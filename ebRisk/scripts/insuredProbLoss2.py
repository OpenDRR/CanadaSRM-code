# Python script to read parquet files from eb_risk CanadaSRM calculations to calculate the EP curve for insured losses, considering secondary perils such as FFE, tsunami, and LQ. 
# Written by TEH in summer 2026.

# TO DO:
#  - Add progress bar for how many eids have been processed out of total number. 
#  - Add more granular insurance parameters! and update script to accommodate. 
#  - Is there a way to parallelize this?
#  - Should I be assigning exposure at the beginning or randomly assigning it after each event? 
#  - figure out how to test this ebrisk output against the unmodified version to ensure total loss is the same. 

# DONE:
#  X check if oq already does insurance? Yes but doesn't include ALE/BI? Focussed on reinsurance. Limits have to be defined in absolute values for each policy, so would need as many policies as assets, had to jerry rig it to consider ALE/BI.. not worth it. 
#  X take out variance if it's 0? done.
#  X Ensure it can handle all regions, as defined by insurance params.
#  X delete/clear temporary dataframes?
#  X ADD LIQ BACK IN
#  X should I replace the pla_loss with LQloss for ins calc? if so, how to keep shake and lq separate? Calling it maximum EQPolicy loss, because they're both in EQ policy but whichever is greatest will apply. Alternately could zero the other loss to allow summing over loss types if needed in future to split them. 
#  X Check what im doing with non-RES-COM properties
#  X Check why Dawson city has no liq_class values (eid=13?). Join issue, fixed. 
#  X Should I make URMs uninsurable? PSy says no.

## Notes from Convo with PLew:
# - could I just load some of the parquet files at a time? How are they separated?
# - Need multiprocessing package, not threading
# - os maxcpu will count cpus and let you take advantage of them all
# - Steps that are sequential could interrupt concurrent processing, can I move more of pre-processing outside of analysis?

# To delete parquet files:
# find . -maxdepth 1 -type f -name "asset_event_losses_*.parquet" -delete


####### USAGE: either define parameters here or call them when running this script. If calling arguments then all three must be provided.
####### Ex: python insuredProbLoss.py [CALC_ID INI_FILENAME COMPUTE_RESOURCE]


### Import statements
import pyarrow.parquet as pq
import glob
import pandas as pd
import numpy as np
import pyarrow.dataset as ds
#from openquake.commonlib import datastore
from openquake.commonlib.datastore import read
import random
import geopandas as gpd
import warnings
import time
import os
import sys
import re
import psutil
import gc
import matplotlib.pyplot as plt


#### Calculation Timer
start_time = time.perf_counter()


#### Set run parameters
if len(sys.argv) < 2:
    print("No arguments were provided - using hard-coded values.")
    CALC_ID = 322 #ebRisk calculation
    INI_FILENAME = "/Users/thobbs/Documents/GitHub/canada-srm2/ebRisk/input/ebRisk_b0_Canada_tinyInsuranceTest.ini"
    COMPUTE_RESOURCE="THlaptop"
elif len(sys.argv) == 4:
    print(f"Arguments provided: {sys.argv[1:]}")
    CALC_ID = int(sys.argv[1])
    INI_FILENAME = sys.argv[2]
    COMPUTE_RESOURCE=sys.argv[3]
else:
    raise RuntimeError(f"Incorrect number of arguments provided: expected 0 or 3.")

# Local file locations
if COMPUTE_RESOURCE == "THlaptop":
    PARQUET_DIR = "/Users/thobbs/Documents/GitHub/canada-srm2/Parquets_firstRun/" #Where parquet files were output from ebRisk
    expofile = '/Users/thobbs/Documents/GitHub/openquake-inputs/exposure/general-building-stock/oqBldgExp_CA.csv'
    #denseCSDs = '/Users/thobbs/Documents/WRITING/EQInsuranceGaps/popdensCSD.txt'
    surfgeolfile = '/Users/thobbs/Documents/gsc_surficial_geology.gdb'
    outdir = '/Users/thobbs/Documents/CanadaSRM-output/probabilistic/current/ebRisk/ins-out' #for result tables
    insParamFile="/Users/thobbs/Documents/CanadaSRM-code/ebRisk/scripts/InsParamsByFSA.csv"
elif COMPUTE_RESOURCE == "AWS":
    PARQUET_DIR = "/scratch/parquet-out"
    expofile = "/work/CanadaSRM-input/current/exposure/oqBldgExp_CA_2025Update.csv"
    #denseCSDs = "/work/CanadaSRM-input/current/exposure/popdensCSD.txt"
    surfgeolfile = "/work/CanadaSRM-input/current/geotech/gsc_surficial_geology.gdb"
    outdir = "/work/CanadaSRM-output/probabilistic/current/ebRisk/ins-out"
    insParamFile="/work/CanadaSRM-code/ebRisk/scripts/InsParamsByFSA.csv"

# Temporary insurance params: penetration rate, deductible, policy limit
#insdic_w_res = {'p': 0.55, 'd': 0.125, 'l': 1.11} #1.883}
#insdic_w_com = {'p': 0.85, 'd': 0.1, 'l': 1.04} #1.883} 
#insdic_e_res = {'p': 0.02, 'd': 0.05, 'l': 1.11} #1.818}
#insdic_e_com = {'p': 0.60, 'd': 0.05, 'l': 1.04} #1.818}
ins_params = pd.read_csv(insParamFile)
RESparams = ins_params[ins_params['LoB'] == 'P']
COMparams = ins_params[ins_params['LoB'] == 'C']

# Misc secondary peril parameters
#make_densecsds = False #Set to True if you need to create a list of csd's with pop density over 3000/km2 ('popdensCSD.txt'). Else assume it exists in location specified above. NOT IN USE YET, for FFE.
LQ_rate = {'p_100': 0.04, 'p_50': 0.09} #probability of having 100% or 50% loss, for bldgs with High/Very High LQ susceptibility
mag_LQ_thresh = 6.5 #minimum magnitude of earthquake to create liquefaction


#### Get/calculate the effective calculation time
number_of_logic_tree_samples, ses_per_logic_tree_path, investigation_time = [int(re.search(r'=\s*(\d+)', l).group(1)) for l in open(INI_FILENAME) if l.startswith(("number_of_logic_tree_samples", "ses_per_logic_tree_path", "investigation_time"))]
eff_time = number_of_logic_tree_samples * ses_per_logic_tree_path * investigation_time


#### Define Post Loss Amplification Factors, applied to SHAKE ONLY
# from https://github.com/gem/oq-engine/blob/master/demos/risk/Reinsurance/pla_model.csv and 
# dictionary of return_period : pla_factor
pla_lookup = pd.DataFrame({
    'RP':  [10, 20, 50, 100, 500, 1000, 1500, 10000],
    'PLA': [1.1, 1.1, 1.2, 1.3, 1.4, 1.5, 2.0, 2.0]})
pla_lookup = pla_lookup.sort_values('RP') #ensure RP is ascending

#### Define FFE scalar
# based on factors from PACICC consultation with industry, for approximation only. 
ffe_lookup = pd.DataFrame({
    'RP':  [0, 250, 500, 1000, 500000],
    'FFE': [0.02, 0.02, 0.05, 0.10, 0.10]}) #must be ascending


#### Define Overall Insurance Calculator
# to be run on RES or COM dataframe, one region at a time
def inscalc(data,TYPE):
    # To use insurance params at the FSA level without needing to break the calc down by FSA, take p_rate chance for each asset instead of assigning properties until p_rate achieved. 
    data['rando'] = np.random.rand(len(data))
    data['ins_val'] = data['totalVal'].where(data['rando'] < data['EQ_Pene'], 0)
    data['unins_loss'] = data['max_EQpolicy_loss'].where(data['ins_val'] > 0, 0) #uninsured amount WITHOUT ALE/BI #was loss_pla
    data['deduc'] = data['ins_val']*data['EQDeducPerc'] #deductible as % of value
    data['ins_loss'] = (data['EQLimPerc']*data['max_EQpolicy_loss']).where(data['rando'] < data['EQ_Pene'], 0) #insured loss: product of limit ratio and loss. #was loss_pla
    data['deduc_gap'] = (data['deduc'] - data['max_EQpolicy_loss']).where((data['deduc'] - data['max_EQpolicy_loss']) > 0,0) #how close is loss to deductible #was loss_pla
    data['claim'] = (data['ins_loss'] - data['deduc']).where((data['ins_loss'] - data['deduc']) > 0, 0) #insured loss above deductible
    data['deduc_paid'] = data['deduc'].where(data['claim'] > data['deduc_gap'], data[['max_EQpolicy_loss', 'deduc']].min(axis=1))
    claim_tot = data['claim'].sum()
    deduc_tot = data['deduc_paid'].sum()
    unins_tot = data['unins_loss'].sum()
    return(claim_tot, deduc_tot, unins_tot)


#### Map liquefaction susceptibility
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    surficial = gpd.read_file(surfgeolfile, layer='geology', engine="pyogrio")

liq_lookup = {#from ChatGPT interpretting Youd&Perkins/FEMA liq susc method
    "A":   "Very High",   # Alluvial sediments
    "Ln":  "Very High",   # Littoral and nearshore sediments
    "GLn": "Very High",   # Glaciolacustrine / littoral
    "Mn":  "Very High",   # Littoral and nearshore sediments
    "GMn": "Very High",   # Littoral and nearshore sediments
    "Lo":  "High",        # Offshore sediments
    "GLo": "High",        # Offshore sediments
    "Mo":  "High",        # Offshore sediments
    "GMo": "High",        # Offshore sediments
    "GFp": "High",        # Outwash plain
    "GFc": "High",        # Ice-contact (often loose sand/gravel)
    "E":   "High",        # Eolian sand
    "C":   "Moderate",    # Colluvium
    "Cv":  "Moderate",    # Colluvial veneer
    "GMv": "Moderate",    # Veneer
    "W":   "Moderate",    # Regolith
    "Wv":  "Moderate",    # Regolith veneer
    "O":   "Low",         # Organic deposits
    "Tb":  "Low",         # Till blanket
    "Tv":  "Low",         # Till veneer
    "Th":  "Low",         # Hummocky till
    "Tm":  "Low",         # Moraine complex
    "R":   "None",        # Bedrock
    "V":   "None",        # Volcanic rock
    "I":   "None"}         # Glacier ice

surficial["liq_class"] = (surficial["label"].map(liq_lookup).fillna("Unknown"))


#### Load exposure data
expo = pd.read_csv(expofile)
#provDict = expo[['pruid','prname']].drop_duplicates() 
#assign east and west pruids
Eprovs = [46, 13, 12, 62, 35, 11, 24, 10] #MB, NU, ON, QC, Martms
Wprovs = [59, 48, 61, 47, 60] #BC, AB, SK, YT, NT in no order


#### Make csv of densely populated census subdivisions
#if make_densecsds == True:
#    expo_master = pd.read_csv('/Users/thobbs/Documents/GitHub/openquake-inputs/exposure/general-building-stock/BldgExpRef_CA_master_v3p2.csv')
#    csds_all = expo_master[['csduid','day','Sauid_km2']].groupby(['csduid']).sum()
#    csds_all['pop_per_km2'] = csds_all['day']/csds_all['Sauid_km2']
#    csds_all = csds_all.sort_values(by='pop_per_km2', ascending=False)
#    csds = csds_all[csds_all['pop_per_km2'] >= 3000].index.values
#    ## save this list
#    np.savetxt(denseCSDs, csds, delimiter=",")
#    del expo_master; gc.collect() #clear up memory by deleting df
#else:
#    csds = np.loadtxt(denseCSDs, delimiter=",")


#### Load loss_by_event table from OQ, for post loss amplification (PLA)
dstore = read(CALC_ID)
loss_by_event = dstore.read_df('risk_by_event')
lbe = loss_by_event[['event_id','loss']].groupby(['event_id']).sum()
del loss_by_event; gc.collect() #clear up memory by deleting df

#### Find PLA for each event id
# based on https://docs.openquake.org/oq-engine/manual/latest/user-guide/outputs/event-based-risk-outputs.html#:~:text=computes%20the%20Probably,eff_time%20is%20respected. and https://github.com/gem/oq-engine/issues/9633
lbe = lbe.sort_values('loss', ascending=False).reset_index()
lbe['RP'] = eff_time/((lbe.index)+1)
lbe['PLA'] = np.interp(lbe['RP'], pla_lookup['RP'], pla_lookup['PLA'], left=1.0, right=pla_lookup['PLA'].iloc[-1])


#### Get source model information for each event
rups = dstore.read_df('ruptures') #read oq ruptures
sources = dstore.read_df('source_info'); sources = sources.reset_index() #read oq sources
events = dstore.read_df('events') #read oq events
events = events.merge(rups[['id', 'source_id', 'mag', 'occurrence_rate']], left_on='rup_id', right_on='id', how='left', suffixes=('','_rup')) #add rupture id from rupture df
events['source_name'] = sources.iloc[events["source_id"]].reset_index(drop=True)['source_id'] #grab source name from sources df, based on rupture id
events['source_name'] = events['source_name'].str.decode("utf-8")
del rups; del sources; gc.collect()


#### Assign asset_id from aid
assetcol = dstore["assetcol"]; assets = assetcol.to_dframe()
lookup = assets[["ordinal","id"]].copy() #grab aid, asset_id (no longer include ss_region)
lookup.rename(columns={"id": "asset_id"},inplace=True)
del assets; gc.collect(); #clear up memory by deleting df
    
    
#### Load parquet file[s]
dataset = ds.dataset(glob.glob(f"{PARQUET_DIR}/asset_event_losses_*.parquet"),format="parquet") #read all parquets in current dir
files = dataset.files; batch_size = 100
parqNum = 0
for i in range(0, len(files), batch_size):
    batch_files = files[i:i + batch_size]
    batch_dataset = ds.dataset(batch_files, format="parquet")
    losses = batch_dataset.to_table().to_pandas()

    print(f"Processing files {i}–{i + len(batch_files) - 1}")
    #print(f"Rows: {len(losses):,}")
    #print(f"Memory: {losses.memory_usage(deep=True).sum() / 1024**3:.2f} GB")
    
    parqNum += 1
    losses = losses[losses['event_id'].isin(lbe['event_id'].values)] #drop events that arent in oq event loss table
    losses = losses[losses['loss'] >= 5000] #drop losses less than 5000 (min asset loss)
    losses.drop(losses[losses.loss_type == 'occupants'].index, inplace=True) #remove occupants losses if they exist
    losses = losses.groupby(["event_id", "aid"])["loss"].sum().reset_index() #merge loss types to get total loss in "loss" column


    #### Initialize results dataframe
    ResTable = pd.DataFrame(columns=['eid', 'RP_GU_EQ', 'mag', 'occ_rate', 'ss_region', 'LOB', "GU_EQOnly_loss", "GU_LQOnly_loss", 'GU_EQLQ_loss', 'ins_EQLQ_loss', 'PH_EQLQ_loss', 'UI_EQLQ_loss']) #event, return period of loss, magnitude, occurrence rate of that rupture, region, line of business, ground up lossese [EQ only, LQ only, higher of EQ/LQ], claimed loss paid by insurer, policy-holder (deductible) loss, and uninsured loss.


    #### Merge loss info with supporting metadata
    losses = losses.merge(lbe[['event_id', 'PLA', 'RP']], how='left', on='event_id') #merge with loss by event table
    losses['loss_pla'] = losses['loss']*losses['PLA'] #get loss with amplification
    losses = losses.merge(events[['id','mag','occurrence_rate','source_name']], how='left', left_on='event_id', right_on='id'); losses = losses.drop(columns = 'id') #add source info 


    #### Calc insured losses for each event
    print('Calculating insured losses by event!')
    # isolate each event
    for eid in losses['event_id'].unique():
        print('debug: working on eid: '+str(eid))
        as_loss_by_event = losses[losses['event_id'] == eid]
        RP = as_loss_by_event['RP'].iloc[0]; mag = as_loss_by_event['mag'].iloc[0]; occ_rate = as_loss_by_event['occurrence_rate'].iloc[0]
        as_loss_by_event = as_loss_by_event.merge(lookup,left_on="aid",right_on="ordinal",how="left") #add asset_id and ss_region to event losses
        missing = as_loss_by_event["asset_id"].isna().sum()
        if missing:
            raise RuntimeError(f"{missing} aids could not be matched") 

        # merge with expo
        as_loss_by_event = as_loss_by_event.merge(expo[['id','structural','nonstructural','contents','number','lon','lat','OccClass','pruid', 'fsauid']], left_on="asset_id", right_on="id", how="left"); as_loss_by_event = as_loss_by_event.drop(columns='id') #add expo

        # assign East (1) and West (2) by province
        as_loss_by_event['ss_region'] = np.select([as_loss_by_event["pruid"].isin(Eprovs), as_loss_by_event["pruid"].isin(Wprovs)], [1, 2], default=np.nan).astype(int)

        for region in as_loss_by_event['ss_region'].unique():
            # split by ss_region
            losreg = as_loss_by_event[as_loss_by_event['ss_region'] == region]
            losreg['totalVal'] = losreg['structural']+losreg['nonstructural']+losreg['contents']

            losreg['LQloss'] = 0.0 # Add liq info, only for events with mag above liq thresh
            if mag >= mag_LQ_thresh:
                #print('debug: Adding liquefaction')
                data_gdf = gpd.GeoDataFrame(losreg, geometry=gpd.points_from_xy(losreg["lon"], losreg["lat"]), crs="EPSG:4617") #assuming lat/lon are in WGS84 would be EPSG:4326
                data_gdf = data_gdf.to_crs(surficial.crs)
                losreg_gdf = gpd.sjoin(data_gdf, surficial[["liq_class", "geometry"]], how="left", predicate="intersects")
                missing = losreg_gdf[losreg_gdf["liq_class"].isna()].drop(columns=["liq_class", "index_right"], errors="ignore")
                if not missing.empty:
                    nearest = gpd.sjoin_nearest(missing, surficial[["liq_class", "geometry"]], how="left", distance_col="distance_to_polygon")
                    losreg_gdf.loc[nearest.index] = nearest

                losreg = pd.DataFrame(losreg_gdf.drop(columns=["geometry", "index_right"]))

                # Calc the liq impact and propagate (careful not to conflate with shake loss)
                # Giving buildings in 'High' or 'Very High' LQ susc to have 4% chance of complete loss and 9% chance of 50% loss
                # May be small numbers so using probability per asset instead of total number of bldgs
                LQ_bldgs = losreg[losreg['liq_class'].isin(['High','Very High'])] 
                for [ind, row] in LQ_bldgs.sample(frac=1).iterrows():
                    rando_val = random.random()
                    if rando_val < LQ_rate['p_100']:
                        losreg.at[ind,'LQloss'] = row['totalVal']
                    elif rando_val < (LQ_rate['p_100']+LQ_rate['p_50']):
                        losreg.at[ind,'LQloss'] = 0.5*row['totalVal']

            losreg['max_EQpolicy_loss'] = np.maximum(losreg['LQloss'], losreg['loss_pla'])

            # Separate RES and COM
            RES = losreg[losreg['OccClass'].isin(['RES1', 'RES2'])]
            COM = losreg[losreg['OccClass'].isin(['RES3A', 'RES3C', 'RES3D', 'RES3B', 'RES3F', 'RES3E','RES3','RES4','RES5', 'RES6', 'COM1', 'COM2','COM3','COM4','COM5','COM6','COM7', 'COM8', 'COM9','COM10','IND1', 'IND2', 'IND3', 'IND4', 'IND5', 'IND6', 'AGR1', 'REL1'])]
            PUB = losreg[~losreg['OccClass'].isin(['RES1', 'RES2','RES3A', 'RES3C', 'RES3D', 'RES3B', 'RES3F', 'RES3E','RES3','RES4','RES5', 'RES6', 'COM1', 'COM2','COM3','COM4','COM5','COM6','COM7', 'COM8', 'COM9','COM10','IND1', 'IND2', 'IND3', 'IND4', 'IND5', 'IND6', 'AGR1', 'REL1'])]

            # Run calculations on each line of business (LOB)
            for TYPE in ['RES','COM','PUB']:
                #print('debug: working on TYPE: '+TYPE)
                # set insurance parameters (p_rate, lim, deduc) by FSA and LoB 
                if TYPE == 'RES':
                    data = RES
                    data = data.merge(RESparams[['FSA','EQDeducPerc','EQLimPerc','EQ_Pene']], how="left", left_on="fsauid", right_on="FSA").drop(columns='FSA')
                elif TYPE == 'COM':
                    data = COM
                    data = data.merge(COMparams[['FSA','EQDeducPerc','EQLimPerc','EQ_Pene']], how="left", left_on="fsauid", right_on="FSA").drop(columns='FSA')
                else:
                    data = PUB

                # Insurance calculation
                if not data.empty:
                    GU_EQLQ_loss = data['max_EQpolicy_loss'].sum() #calc ground up (no BI/ALE) EQ/LQ losses (keep higher of EQ/LQ)
                    GU_EQOnly_loss = data['loss_pla'].sum() #calc ground up (no BI/ALE) EQ  only losses
                    GU_LQOnly_loss = data['LQloss'].sum() #calc ground up (no BI/ALE) LQ only loss
                    ######################################################
                    ########## Would have added FFE here if doing more complex treatment, for csd's with (pop dens > 3000p/km2) and MMI>=6 (or existence of moderate damage?). Instead added below as modifier at the end. 
                    #####################################################
                    if TYPE == 'PUB':
                        claim_tot = 0; deduc_tot = 0; unins_tot = GU_EQLQ_loss
                    else:
                        [claim_tot, deduc_tot, unins_tot] = inscalc(data,TYPE) #run insurance calculation
                        ############ In theory could run this multiple times and take the average
                    ResTable.loc[len(ResTable)] = [eid, RP, mag, occ_rate, region, TYPE, GU_EQOnly_loss, GU_LQOnly_loss, GU_EQLQ_loss, claim_tot, deduc_tot, unins_tot] # add info to result table


    #### Sum insured loss by LOB for total event loss, add auto loss and sum shake total
    summary = ResTable.groupby(["eid", "RP_GU_EQ", 'mag', 'occ_rate', "ss_region"])[["GU_EQOnly_loss", "GU_LQOnly_loss", "GU_EQLQ_loss","ins_EQLQ_loss","PH_EQLQ_loss","UI_EQLQ_loss"]].sum().reset_index()
    summary['auto_EQLQ_loss'] = (0.004*summary['GU_EQLQ_loss'])/0.996 #auto is 0.04% per PACICC - I'm making it a % of GU not ins only
    summary['EQLQTotal'] = summary['ins_EQLQ_loss']+summary['PH_EQLQ_loss']+summary['UI_EQLQ_loss']+summary['auto_EQLQ_loss']




    #### Add FFE Loss
    summary['FFE_factor'] = np.interp(summary['RP_GU_EQ'], ffe_lookup['RP'], ffe_lookup['FFE'])
    summary['FFE_loss'] = ((summary['EQLQTotal'])/(1-summary['FFE_factor']))-summary['EQLQTotal']


    #### Add Tsunami Loss
    # based on AIR, for CASCADIA INTERFACE only: it represents (4273/49972) of total losses (including ALE/BI) and (1117/17078) of insured losses (seems to have already subtracted deductible, so only applying to "ins").
    # Isolate CSZ events
    CSZ_eids = events[events['source_name'].str.contains('CIS')]['id'].values
    # Add tsunami for those events
    summary['tot_tsunami'] = 0; summary['ins_tsunami'] = 0
    for eid in CSZ_eids:
        if summary[summary['eid'] == eid].index.values:
            for ind_val in summary[summary['eid'] == eid].index.values:
                summary.at[ind_val, 'tot_tsunami'] = summary.iloc[ind_val]['EQLQTotal']*(4273/49972)
                summary.at[ind_val, 'ins_tsunami'] = summary.iloc[ind_val]['ins_EQLQ_loss']*(1117/17078)


    #### Calculate total cost to the insurance sector
    summary['TotCostToIns'] = summary['ins_tsunami']+summary['ins_EQLQ_loss']+summary['auto_EQLQ_loss']+summary['FFE_loss']
    # get the RP of the insured loss
    ilbe = summary[['eid','TotCostToIns']].sort_values('TotCostToIns', ascending=False).reset_index()
    ilbe['RP_Ins'] = eff_time/((ilbe.index)+1)
    summary = summary.merge(ilbe[['eid','RP_Ins']], how='left', on='eid')


    #### Save Results
    ResTable.to_csv(outdir+'/Shake_by_LOB_'+str(CALC_ID)+'_'+str(parqNum)+'.csv')
    summary.to_csv(outdir+'/Summary_'+str(CALC_ID)+'_'+str(parqNum)+'.csv')

    del losses; del batch_dataset; del summary; del ResTable; del RES; del COM; del PUB; del data; del as_loss_by_event; del losreg

##### Plot EP Curve - NATIONAL, EAST, WEST - WORKING HERE.
#plt.figure(figsize=(5, 5))
#plt.scatter(summary['RP_Ins'], summary['TotCostToIns'])
## make this a log plot, color by GU loss to show that they're totally unrelated. 
## add axis labels
#plt.title('Insured Loss EP Curve')
#plt.savefig(outdir+'/SummaryEP_'+str(CALC_ID)+'.png')


#### End Calc Timer
end_time = time.perf_counter()
execution_time = end_time - start_time
print(f"Execution time: {execution_time:.6f} seconds")


