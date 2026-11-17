# Python script to aggregate insProbLoss output csv's and create RP curves/files. Written by TEH in Aug 2026.
######## USAGE
######## > python aggInsProbLoss.py CALC_ID INI_FILENAME COMPUTE_RESOURCE
######## where INI_FILENAME is the filename only (without path) and COMPUTE_RESOURCE is either 'AWS' or 'THlaptop'.


####################################################################
########## IMPORT AND CONFIGS
####################################################################

import glob
import pandas as pd
import re
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter, LogLocator, FixedLocator
import sys
from collections import defaultdict

#### Configuration - USER SPECIFIED 
RPs = np.array([100, 200, 250, 300, 400, 500, 600, 700, 800, 900, 1000, 1250, 1500, 1650, 1750, 2000, 2250, 2475, 2750, 3000, 3300, 3500, 4000, 4500, 5000, 6000, 7000, 8000, 9000, 10000, 20000, 40000, 50000, 60000, 80000, 100000])
percs = np.array([0.05, 0.95]) #specify only 2, in order (currently setup to take 'low' as the second number and 'high' as the first number). Meaning is "5% of realizations have higher loss than the 0.05 perc".

CALC_ID = 43
INI_FILENAME = "/Users/thobbs/Documents/CanadaSRM-code/ebRisk/input/ebRisk_b0_Canada_1Myr_Expo2025.ini"
insoutDir = '/Users/thobbs/Documents/CanadaSRM-output/probabilistic/current/ebRisk/ins-out'

CALC_ID = int(sys.argv[1])
INI_FILENAME_short = sys.argv[2]
compute_resource = sys.argv[3]
if compute_resource == 'AWS':
    iniDir = "/work/CanadaSRM-code/ebRisk/input/"
    insoutDir = "/work/CanadaSRM-output/probabilistic/current/ebRisk/ins-out"
elif compute_resource == 'THlaptop':
    iniDir = "/Users/thobbs/Documents/CanadaSRM-code/ebRisk/input/"
    insoutDir = '/Users/thobbs/Documents/CanadaSRM-output/probabilistic/current/ebRisk/ins-out'

INI_FILENAME = str(iniDir)+str(INI_FILENAME_short)

#### Plotting configs
region_colors = {'East': 'darkblue', 'West': 'darkgreen', 'Natl': 'indigo', 'RAWOQ_GU_EQ_LOSS': 'darkred'}
loss_styles = {'GU_EQOnly_loss': ':', 'TotCostToIns': '-', 'TotCostNotIns': '-.', 'TOT':'--', 'loss_with_PLA': '-'}
loss_names = {'GU_EQOnly_loss': 'GU Shake-only Loss before Insurance Applied', 'TotCostToIns': 'Portion of Total Loss Paid by Insurer', 'TotCostNotIns': 'Portion of Total Loss Paid by Property Owner', 'TOT':'Total Loss from Shake, Liq, Tsun, FFE', 'loss_with_PLA': 'Raw OQ GU Shake-only Loss with PLA'}

####################################################################
########## DEFINE FUNCTIONS
####################################################################

#### Define RP function
# assumes all events from catalogue time are in 'data'
def get_RP(data, eff_time, loss_type):
    loss_by_year = data[['GU_EQOnly_loss',
       'GU_LQOnly_loss', 'GU_EQLQ_loss', 'ins_EQLQ_loss', 'PH_EQLQ_loss',
       'UI_EQLQ_loss', 'auto_EQLQ_loss', 'EQLQTotal', 'FFE_loss',
       'tot_tsunami', 'ins_tsunami', 'TotCostToIns', 'TotCostNotIns', 'TOT', 'year']].groupby('year').sum().reset_index()
    for l in loss_type:
        ranked = loss_by_year[['year', str(l)]].sort_values(by=str(l), ascending=False).reset_index()
        ranked['RP-year-'+str(l)] = eff_time/((ranked.index)+1)
        loss_by_year = loss_by_year.merge(ranked[['year','RP-year-'+str(l)]], how='left', on='year')
    
    return loss_by_year

#### Define function to interpolate the RPs
def interpolate_RP_losses(df, RPs, RPcolumn, rlz):
    df = df.sort_values(RPcolumn)
    LOSScolumn = RPcolumn.split('-')[2]
    return pd.DataFrame({
        'rlz': RPs,
        rlz: np.interp(
            np.log(RPs),
            np.log(df[RPcolumn]),
            df[LOSScolumn]
        )
    }).set_index('rlz').T


#### Define plotting function
def plot_with_uncert(out_df, full, regs, typ, CALC_ID):
    fig, ax = plt.subplots(figsize=(10, 7))
    for r in regs:
        low = out_df[(out_df['Region'] == r) & (out_df['Loss_Type'] == typ) & (out_df['Percentile'] == percs[1])][['RP', 'Loss']].reset_index(drop=True)
        high = out_df[(out_df['Region'] == r) & (out_df['Loss_Type'] == typ) & (out_df['Percentile'] == percs[0])][['RP', 'Loss']].reset_index(drop=True)
        full_RP = full[f'{r}'][['RP-year-'+str(typ), str(typ)]].sort_values('RP-year-'+str(typ))
        x = pd.to_numeric(low['RP'], errors='coerce').to_numpy(dtype=float)
        ax.fill_between(x, low['Loss']/1e9, high['Loss']/1e9, alpha=0.1, color=region_colors[str(r)], label=f'5-95th percentile loss for {r} - {typ}') #plot uncertainty band
        ax.plot(x, low['Loss']/1e9, marker="", color=region_colors[str(r)], linestyle=loss_styles[str(typ)], linewidth=0.5)
        ax.plot(x, high['Loss']/1e9, marker="", color=region_colors[str(r)], linestyle=loss_styles[str(typ)], linewidth=0.5)
        ax.plot(full_RP['RP-year-'+str(typ)], full_RP[str(typ)]/1e9, marker="", color=region_colors[str(r)], linestyle=loss_styles[str(typ)], label=f'{r} - {typ}') 
    
    ax.set_xscale("log"); ax.set_yscale("log")
    xlimset = [100, 6000]; ylimset = [7, 1000]
    ax.set_xlim(xlimset); ax.set_ylim(ylimset)
    ax.set_xlabel("Return Period [years]", fontsize=12)
    ax.set_ylabel("Loss [billions of dollars]", fontsize=12)
    # Human-readable tick labels
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:,.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, pos: f"${y:g}B"))
    # Add sensible log tick locations
    ticks = np.concatenate([np.arange(0, 12, 2), np.arange(20, 120, 20), np.arange(200, 1200, 200), np.arange(2000, 12001, 2000)])
    ax.xaxis.set_major_locator(FixedLocator(ticks)); ax.yaxis.set_major_locator(FixedLocator(ticks))
    # Grid and legend
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=11)
    plt.tight_layout()
    #plt.show()
    plt.savefig(insoutDir+'/EP_'+typ+'_'+str(CALC_ID)+'.png')



####################################################################
########## LOAD DATA AND ADJUST
####################################################################

#### Read csvs
events = pd.read_csv(str(insoutDir)+'/events_for_'+str(CALC_ID)+'.csv')
df = pd.concat([pd.read_csv(f) for f in glob.glob(str(insoutDir) + '/Summary_' + str(CALC_ID) + '_2026*.csv')], ignore_index=True)


#### get rid of 'RP_EQ-year', add cost to not insurance
df = df[['eid', 'year', 'mag', 'occ_rate',
       'ss_region', 'GU_EQOnly_loss', 'GU_LQOnly_loss', 'GU_EQLQ_loss',
       'ins_EQLQ_loss', 'PH_EQLQ_loss', 'UI_EQLQ_loss', 'auto_EQLQ_loss',
       'EQLQTotal', 'FFE_loss', 'tot_tsunami', 'ins_tsunami',
       'TotCostToIns']]
df['TotCostNotIns'] = df['PH_EQLQ_loss'] + df['UI_EQLQ_loss'] + (df['tot_tsunami']-df['ins_tsunami'])
df = df.merge(events[['id', 'rlz_id']], left_on = 'eid', right_on = 'id', how='left').drop(columns='id') # add rlz_id to df


#### Get/calculate the effective calculation time
number_of_logic_tree_samples, ses_per_logic_tree_path, investigation_time = [int(re.search(r'=\s*(\d+)', l).group(1)) for l in open(INI_FILENAME) if l.startswith(("number_of_logic_tree_samples", "ses_per_logic_tree_path", "investigation_time"))]
eff_time = number_of_logic_tree_samples * ses_per_logic_tree_path * investigation_time 


#### Isolate east, west, natl
# Only keep useful columns
east = df[df['ss_region'] == 1]; east['TOT'] = east['TotCostToIns'] + east['TotCostNotIns']
west = df[df['ss_region'] == 2]; west['TOT'] = west['TotCostToIns'] + west['TotCostNotIns']
national = df.groupby(['eid','year','mag','occ_rate','rlz_id'], as_index=False).sum() #combine east and west
national['TOT'] = national['TotCostToIns'] + national['TotCostNotIns']
dfs_regs = {'East': east, 'West': west, 'Natl': national}

####################################################################
########## CALCULATE RPs
####################################################################

#### For each of [east, west, national], for each rlz_id, for each loss type, calculate the RP and save it in a new df.

regs = ['East', 'West', 'Natl']
loss_type = ['GU_EQOnly_loss', 'TotCostToIns', 'TotCostNotIns', 'TOT']
num_rlz = len(events['rlz_id'].unique()) #tot number of rlz to iterate over 

#init dfs and add RP losses by rlz to each one
full = {
    f'{reg}': pd.DataFrame() for reg in regs}
dfs = {f'{reg}_{typ}': pd.DataFrame() for reg in regs
    for typ in loss_type}
for reg in regs:
    df_regional = dfs_regs[reg] #grab the regional df
    full[f'{reg}'] = get_RP(df_regional, eff_time, loss_type)
    for rlz in events['rlz_id'].unique():
        df_temp = df_regional[df_regional['rlz_id'] == rlz] #isolate rlz
        temp_RP = get_RP(df_temp, eff_time/num_rlz, loss_type) # Get RP loss
        for typ in loss_type:
            df_name = f'{reg}_{typ}'
            RPcolumn = 'RP-year-'+typ
            new_df = interpolate_RP_losses(temp_RP, RPs, RPcolumn, rlz)
            dfs[df_name] = pd.concat([dfs[df_name], new_df])


#### For each df, for each RP, find the 5% and 95% losses. 
out_df = pd.DataFrame(columns=['Region', 'Loss_Type', 'Percentile', 'RP', 'Loss'])
for typ in loss_type:
    for reg in regs:
        df_name = f'{reg}_{typ}'
        for perc in percs:
            for RP in RPs:
                loss_set = dfs[df_name][RP].sort_values(ascending=False, ignore_index=True)
                num_rlz_higher = np.minimum(int(np.round(perc*num_rlz)), (len(loss_set)-1)) #make sure it can't call a higher index than length
                loss_perc = loss_set[num_rlz_higher] #bc python is 0-indexed I don't need to add one.
                newline = pd.DataFrame([{'Region': reg, 'Loss_Type': typ, 'Percentile': perc, 'RP': RP, 'Loss': loss_perc}])
                out_df = pd.concat([out_df, newline])
    
    plot_with_uncert(out_df, full, regs, typ, CALC_ID)



####################################################################
########## EXPORT RESULTS
####################################################################

#### Calc interpolated 'full' values (didn't do this earlier because want to plot all the data, but too big to bother saving.)
for typ in loss_type:
    for reg in regs:
        RPcolumn = 'RP-year-'+typ
        new_df = interpolate_RP_losses(full[f'{reg}'], RPs, RPcolumn, 'full')
        for RP in RPs:
            newline = pd.DataFrame([{'Region': reg, 'Loss_Type': typ, 'Percentile': 'full', 'RP': RP, 'Loss': new_df[RP].values[0]}])
            out_df = pd.concat([out_df, newline])

#### Export data
out_df.to_csv(str(insoutDir)+'/RP_Full_Perc_Results_'+str(CALC_ID)+'.csv')

exit()














##########################################################################
########################################### STUFF FROM OLD SCRIPT THAT I HAVEN'T ADJUSTED YET
#### Get losses from OQ event_loss_table, add PLA, and ensure it matches GU_EQOnly from ins calcs
loss_type = ['loss_with_PLA']
events['RP-year-loss'] = events['RP-year']
events['loss_with_PLA'] = events['loss']*events['PLA']
events_by_year = events.groupby(['RP-year-loss','year'])['loss_with_PLA'].sum().reset_index()
events_by_year.attrs['name'] = 'RAWOQ_GU_EQ_LOSS'
regions = [events_by_year]
plot_EP(regions, loss_type, loss_thresh, xlimset, ylimset)




# west_RP.sort_values(by='RP-year-TotCostToIns', ascending=False).head(100).to_csv(str(insoutDir)+'/west_sample_RPresult_'+str(CALC_ID)+'.csv')







########################### SCRAPS
# used this to get the ylim for the EP curves
ylimup = 0; ylimdown = 100000
for r in regions:
        for l in loss_type:
            closest_max = (r['RP-year-'+l] - xlimset[1]).abs().idxmin()
            u = r.loc[closest_max, l]/1e9
            closest_min = (r['RP-year-'+l] - xlimset[0]).abs().idxmin()
            d = r.loc[closest_min, l]/1e9
            ylimup = np.maximum(ylimup,u); ylimdown = np.minimum(ylimdown, d)

ylimset = [np.floor(ylimdown), np.ceil(ylimup/100)*100]









################## plotting losses by source zone, region to figure out why eastern losses are so high and why liq losses are so high for M9.1 CSZ
#df = pd.concat([pd.read_csv(f) for f in glob.glob('./Summary_40_2026*.csv')], ignore_index=True)
ev = pd.read_csv('events_for_40.csv')
ev[['sourcename','dummy']] = ev['source_name'].str.split(";", expand=True)
df['sourcename'] = df['eid'].map(ev.set_index('id')['sourcename'])
res = df[['eid', 'year', 'mag', 'occ_rate', 'ss_region', 'GU_EQOnly_loss', 'GU_LQOnly_loss','sourcename']]

eq = res.groupby(['sourcename','ss_region'])['GU_EQOnly_loss'].sum().reset_index().sort_values('GU_EQOnly_loss')
lq = res.groupby(['sourcename','ss_region'])['GU_LQOnly_loss'].sum().reset_index().sort_values('GU_LQOnly_loss')

eq.groupby('ss_region')['GU_EQOnly_loss'].sum()
#ss_region
#1    6.903627e+13 EAST
#2    6.383101e+13 WEST

lq.groupby('ss_region')['GU_LQOnly_loss'].sum()
#ss_region
#1    1.001988e+14 EAST
#2    7.606076e+13 WEST

from openquake.commonlib.datastore import read
dstore = read(40)
sources = dstore.read_df('source_info')
events = dstore.read_df('events')
rups = dstore.read_df('ruptures')

#USE RUPS TO PLOT LQ losses by hypocentre?
#PROB BEST TO CHANGE LIQ CALC TO VERY HIGH ONLY, BUT CAN'T DO WITHOUT RERUNNING INS CALC

for eid in df[['eid','GU_LQOnly_loss']].sort_values('GU_LQOnly_loss').tail(5)['eid'].values:
    rupid = ev[ev['id'] == eid]['rup_id'].values[0]
    ruplat = rups[rups['id'] == rupid]['hypo_1'].values[0]
    ruplon = rups[rups['id'] == rupid]['hypo_0'].values[0]
    rup = gpd.GeoSeries([gpd.points_from_xy([ruplon], [ruplat])[0]], crs="EPSG:4326").to_crs(canada_crs)
    x, y = rup.geometry.x.iloc[0], rup.geometry.y.iloc[0]
    
    ax.scatter(x, y, s=rupmag**2 * 2, facecolor="white", edgecolor="black", linewidth=0.7, zorder=10)



