# Python script to read avg asset loss results from scenario CanadaSRM calculations to calculate the insured losses, considering secondary perils such as FFE, tsunami, and LQ. 
# Written by TEH in summer 2026, modified from insuredProbLoss2.py.

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


####### USAGE: either define parameters here or call them when running this script. If calling arguments then all three must be provided.
####### Ex: python insuredDetLoss.py [CALC_ID INI_FILENAME COMPUTE_RESOURCE]

# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
### YOU MUST RUN THIS FROM THE SAME PLACE AS YOU RAN THE CALC (CanadaSRM-output/deterministic/current/)!
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!


### Import statements
import glob
import pandas as pd
import numpy as np
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
import configparser
import xml.etree.ElementTree as ET


#### Calculation Timer
start_time = time.perf_counter()


#### Set run parameters
if len(sys.argv) < 2:
    print("No arguments were provided - using hard-coded values.")
    CALC_ID = 28 #ebRisk calculation
    INI_FILENAME = "/Users/thobbs/Documents/CanadaSRM-code/scenario/input/s_Risk_SIM9p2_CascadiaInterfaceBestFault_b0_b.ini"
    COMPUTE_RESOURCE="THlaptop"
elif len(sys.argv) == 4:
    print(f"Arguments provided: {sys.argv[1:]}")
    CALC_ID = int(sys.argv[1])
    INI_FILENAME = sys.argv[2]
    COMPUTE_RESOURCE=sys.argv[3]
else:
    raise RuntimeError(f"Incorrect number of arguments provided: expected 0 or 3.")

# Local file locations
config = configparser.ConfigParser()
config.read(INI_FILENAME)
expofile = config["Exposure model"]["exposure_file"]
if COMPUTE_RESOURCE == "THlaptop":
    #expofile = '/Users/thobbs/Documents/CanadaSRM-input/current/exposure/oqBldgExp_CA_2025Update.csv'
    #denseCSDs = '/Users/thobbs/Documents/WRITING/EQInsuranceGaps/popdensCSD.txt'
    surfgeolfile = '/Users/thobbs/Documents/CanadaSRM-input/current/geotech/gsc_surficial_geology.gdb'
    indir = '/Users/thobbs/Documents/CanadaSRM-output/deterministic/current/temp' #raw OQ exports
    outdir = '/Users/thobbs/Documents/CanadaSRM-output/deterministic/current/ins-out' #for result tables
    insParamFile="/Users/thobbs/Documents/CanadaSRM-code/ebRisk/scripts/InsParamsByFSA.csv"
elif COMPUTE_RESOURCE == "AWS":
    #expofile = "/work/CanadaSRM-input/current/exposure/oqBldgExp_CA_2025Update.csv"
    #denseCSDs = "/work/CanadaSRM-input/current/exposure/popdensCSD.txt"
    surfgeolfile = "/work/CanadaSRM-input/current/geotech/gsc_surficial_geology.gdb"
    indir = '/work/CanadaSRM-output/probabilistic/current/temp'
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

# Provide APPROXIMATE return periods and source loc for scenarios, for PLA, FFE and TSUNAMI ONLY (below)
scen_lookup = pd.DataFrame({
    'scen': ['SIM9p1_CascadiaInterfaceBestFault', 'SIM9p2_CascadiaInterfaceBestFault', 'SCM7p5_MontrealIapetan', 'SCM5p8_MontrealIapetan', 'ACM7p0_GeorgiaStraitASHOCK'],
    'RP': [500, 700, 10000, 4000, 2000],
    'sourcezone': ['CSZ', 'CSZ', 'SC', 'SC', 'AC']})
scenName = INI_FILENAME.split('_Risk_')[1].split('_b0')[0] ### NOTE: THIS ASSUMES BASELINE ONLY
RP = scen_lookup['RP'][scen_lookup['scen'] == scenName].values[0]


#### Define Post Loss Amplification Factors, applied to SHAKE ONLY
# from https://github.com/gem/oq-engine/blob/master/demos/risk/Reinsurance/pla_model.csv and 
# dictionary of return_period : pla_factor
pla_lookup = pd.DataFrame({
    'RP':  [10, 20, 50, 100, 500, 1000, 1500, 10000],
    'PLA': [1.1, 1.1, 1.2, 1.3, 1.4, 1.5, 2.0, 2.0]})
pla_lookup = pla_lookup.sort_values('RP') #ensure RP is ascending


#### Find PLA for provided approximate RP
PLA = np.interp(RP, pla_lookup['RP'], pla_lookup['PLA'], left=1.0, right=pla_lookup['PLA'].iloc[-1])


#### Define Overall Insurance Calculator
# to be run on RES or COM dataframe, one region at a time
def inscalc(data,TYPE):
    # To use insurance params at the FSA level without needing to break the calc down by FSA, take p_rate chance for each asset instead of assigning properties until p_rate achieved. 
    data['rando'] = np.random.rand(len(data))
    data['ins_val'] = data['totalVal'].where(data['rando'] < data['EQ_Pene'], 0)
    data['unins_loss'] = data['max_EQpolicy_loss'].where(data['ins_val'] == 0, 0) #uninsured amount WITHOUT ALE/BI #was loss_pla
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

#### Initialize results dataframe
ResTable = pd.DataFrame(columns=['APPROX_EQ_RP', 'mag', 'LOB', "GU_EQOnly_loss", "GU_LQOnly_loss", 'GU_EQLQ_loss', 'ins_EQLQ_loss', 'PH_EQLQ_loss', 'UI_EQLQ_loss']) #event, return period of loss, magnitude, occurrence rate of that rupture, region, line of business, ground up lossese [EQ only, LQ only, higher of EQ/LQ], claimed loss paid by insurer, policy-holder (deductible) loss, and uninsured loss.


#### Get source model information 
rupfile = config["Rupture information"]["rupture_model_file"]
mag = float(ET.parse(rupfile).find(".//{*}magnitude").text)
source = scen_lookup['sourcezone'][scen_lookup['scen'] == scenName].values[0]


#### Load exposure data
expo = pd.read_csv((expofile.split('.xml')[0])+'.csv')


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


#### Load results from avg asset losses export
losses = pd.read_csv(indir+'/avg_losses-mean_'+str(CALC_ID)+'.csv', skiprows=1)
losses.drop(columns=['occupants', 'BldEpoch', 'GenOcc', 'LandUse', 'SAC', 'SSC_Zone', 'ss_region'], inplace=True) # remove stuff we def don't need
losses['loss'] = losses['contents']+losses['nonstructural']+losses['structural']
# Drop lines with no impact - if no loss in csd
csd_keep = losses.groupby('csduid')['loss'].sum().loc[lambda x: x > 0].index.tolist()
as_loss_by_event = losses[losses['csduid'].isin(csd_keep)].copy()
as_loss_by_event['loss_pla'] = as_loss_by_event['loss']*PLA #get loss with amplification
as_loss_by_event = as_loss_by_event.merge(expo[['id','structural','nonstructural','contents','number']], left_on="asset_id", right_on="id", how="left", suffixes=('_loss', '_val')); as_loss_by_event = as_loss_by_event.drop(columns='id') #add expo
del expo; del losses; gc.collect(); #clear up memory by deleting dfs


#### Calc insured losses for each event
print('Calculating insured losses')
losreg = as_loss_by_event
losreg['totalVal'] = losreg['structural_val']+losreg['nonstructural_val']+losreg['contents_val']
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
        ResTable.loc[len(ResTable)] = [RP, mag, TYPE, GU_EQOnly_loss, GU_LQOnly_loss, GU_EQLQ_loss, claim_tot, deduc_tot, unins_tot] # add info to result table


#### Sum insured loss by LOB for total event loss, add auto loss and sum shake total
summary = ResTable.groupby(["APPROX_EQ_RP", 'mag'])[["GU_EQOnly_loss", "GU_LQOnly_loss", "GU_EQLQ_loss","ins_EQLQ_loss","PH_EQLQ_loss","UI_EQLQ_loss"]].sum().reset_index()
summary['auto_EQLQ_loss'] = (0.004*summary['GU_EQLQ_loss'])/0.996 #auto is 0.04% per PACICC - I'm making it a % of GU not ins only
summary['EQLQTot_withAuto'] = summary['ins_EQLQ_loss']+summary['PH_EQLQ_loss']+summary['UI_EQLQ_loss']+summary['auto_EQLQ_loss']

 


#### Add FFE Loss
# based on factors from PACICC consultation with industry, for approximation only. 
ffe_lookup = pd.DataFrame({
    'RP':  [0, 250, 500, 1000, 500000],
    'FFE': [0.02, 0.02, 0.05, 0.10, 0.10]}) #must be ascending
summary['FFE_factor'] = np.interp(summary['APPROX_EQ_RP'], ffe_lookup['RP'], ffe_lookup['FFE'])
summary['FFE_loss'] = ((summary['EQLQTot_withAuto'])/(1-summary['FFE_factor']))-summary['EQLQTot_withAuto']


#### Add Tsunami Loss
# based on AIR, for CASCADIA INTERFACE only: it represents (4273/49972) of total losses (including ALE/BI) and (1117/17078) of insured losses (seems to have already subtracted deductible, so only applying to "ins").
summary['tot_tsunami'] = 0; summary['ins_tsunami'] = 0
# Isolate CSZ events
if source == 'CSZ':
    # Add tsunami for this event
    summary['tot_tsunami'] = summary['EQLQTot_withAuto']*(4273/49972)
    summary['ins_tsunami'] = summary['ins_EQLQ_loss']*(1117/17078)


#### Calculate total cost to the insurance sector
summary['TotCostToIns'] = summary['ins_tsunami']+summary['ins_EQLQ_loss']+summary['auto_EQLQ_loss']+summary['FFE_loss']
summary['TotCost_EQLQAutoSecPerils'] = summary['EQLQTot_withAuto'] + summary['tot_tsunami'] + summary['FFE_loss']


#### Save Results
ResTable.to_csv(outdir+'/Shake_by_LOB_'+str(CALC_ID)+'.csv')
summary.to_csv(outdir+'/Summary_'+str(CALC_ID)+'.csv')


#### End Calc Timer
end_time = time.perf_counter()
execution_time = end_time - start_time
print(f"Execution time: {execution_time:.6f} seconds")


