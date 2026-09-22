# Python script to aggregate insProbLoss output csv's and create RP curves/files. Written by TEH in Aug 2026.

import glob
import pandas as pd
import re
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter, LogLocator
import sys

#### Configuration - USER SPECIFIED
CALC_ID = 34
INI_FILENAME = "/Users/thobbs/Documents/CanadaSRM-code/ebRisk/input/ebRisk_b0_Canada_500kyr_Expo2025.ini"
#CALC_ID = int(sys.argv[1])
#INI_FILENAME = sys.argv[2]
insoutDir = '/Users/thobbs/Documents/CanadaSRM-output/probabilistic/current/ebRisk/ins-out'
loss_thresh = 1e6 #don't keep annual losses lower than this in loss_by_year outputs
# could rewrite above param so it keeps any line with ins or unins total loss >.

###################### NEED TO FIX BELOW TO DO YEAR NOT EVENT - Did I already??
#### Define RP function
# assumes all events from catalogue time are in 'data'
def get_RP(data, eff_time, loss_type):
    loss_by_year = data[['GU_EQOnly_loss',
       'GU_LQOnly_loss', 'GU_EQLQ_loss', 'ins_EQLQ_loss', 'PH_EQLQ_loss',
       'UI_EQLQ_loss', 'auto_EQLQ_loss', 'EQLQTotal', 'FFE_loss',
       'tot_tsunami', 'ins_tsunami', 'TotCostToIns', 'TotCostNotIns', 'year']].groupby('year').sum().reset_index()
    for l in loss_type:
        ranked = loss_by_year[['year', str(l)]].sort_values(by=str(l), ascending=False).reset_index()
        ranked['RP-year-'+str(l)] = eff_time/((ranked.index)+1)
        loss_by_year = loss_by_year.merge(ranked[['year','RP-year-'+str(l)]], how='left', on='year')
    
    loss_by_year = loss_by_year[loss_by_year[loss_type].gt(loss_thresh).any(axis=1)]
    return loss_by_year


#### Define plotting function
def plot_EP(regions, loss_type, loss_thresh):
    region_colors = {'East': 'darkblue', 'West': 'darkgreen', 'Natl': 'indigo', 'RAWOQ_GU_EQ_LOSS': 'darkred'}
    loss_styles = {'GU_EQOnly_loss': ':', 'TotCostToIns': '-', 'TotCostNotIns': '--', 'loss': '-'}
    fig, ax = plt.subplots(figsize=(10, 7))
    # Plot the three datasets per loss_type
    for l in loss_type:
        for r in regions:
            r = r[r[str(l)] > loss_thresh].sort_values(by=('RP-year-'+str(l)))
            region = r.attrs.get('name')
            ax.plot(r['RP-year-'+str(l)], r[str(l)] / 1e9, marker="", color=region_colors[str(region)], linestyle=loss_styles[str(l)], label=f'{region}-{l}')
    
    # Log-log axes
    ax.set_xscale("log"); ax.set_yscale("log")
    # Axis labels
    ax.set_xlabel("Return Period [years]", fontsize=12)
    ax.set_ylabel("Loss [billions of dollars]", fontsize=12)
    # Human-readable tick labels
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda x, pos: f"{x:,.0f}")
    )
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda y, pos: f"${y:g}B")
    )
    # Add sensible log tick locations
    ax.yaxis.set_major_locator(LogLocator(base=10)); ax.xaxis.set_major_locator(LogLocator(base=10))
    # Grid and legend
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=11)
    plt.tight_layout()
    #plt.show()
    if (len(loss_type) == 1) & (loss_type[0] == 'loss'):
        plt.savefig(insoutDir+'/'+regions[0].attrs.get('name')+'_'+str(CALC_ID)+'.png')
    else:
        plt.savefig(insoutDir+'/Result_'+str(CALC_ID)+'.png')


#### Read csvs
events = pd.read_csv(str(insoutDir)+'/events_for_'+str(CALC_ID)+'.csv')
df = pd.concat([pd.read_csv(f) for f in glob.glob(str(insoutDir) + '/Summary_' + str(CALC_ID) + '_2026*.csv')], ignore_index=True)


#### Add 'year' back, get rid of 'eff_year'
df = df[['eid', 'mag', 'occ_rate',
       'ss_region', 'GU_EQOnly_loss', 'GU_LQOnly_loss', 'GU_EQLQ_loss',
       'ins_EQLQ_loss', 'PH_EQLQ_loss', 'UI_EQLQ_loss', 'auto_EQLQ_loss',
       'EQLQTotal', 'FFE_loss', 'tot_tsunami', 'ins_tsunami',
       'TotCostToIns']]
df['TotCostNotIns'] = df['PH_EQLQ_loss'] + df['UI_EQLQ_loss'] + (df['tot_tsunami']-df['ins_tsunami'])
df['year'] = df['eid'].map(events.set_index('id')['year'])


#### Get/calculate the effective calculation time
number_of_logic_tree_samples, ses_per_logic_tree_path, investigation_time = [int(re.search(r'=\s*(\d+)', l).group(1)) for l in open(INI_FILENAME) if l.startswith(("number_of_logic_tree_samples", "ses_per_logic_tree_path", "investigation_time"))]
eff_time = number_of_logic_tree_samples * ses_per_logic_tree_path * investigation_time


#### Isolate east, west, natl
# Only keep useful columns
east = df[df['ss_region'] == 1]
west = df[df['ss_region'] == 2]
national = df.groupby(['eid','year','mag','occ_rate'], as_index=False).sum() #combine east and west


#### Get insured RPs and plot
loss_type = ['GU_EQOnly_loss', 'TotCostToIns', 'TotCostNotIns'] #can be a single type or multiple
east_RP = get_RP(east, eff_time, loss_type); east_RP.attrs['name'] = 'East'
west_RP = get_RP(west, eff_time, loss_type); west_RP.attrs['name'] = 'West'
national_RP = get_RP(national, eff_time, loss_type); national_RP.attrs['name'] = 'Natl'
regions = [east_RP, west_RP, national_RP]
plot_EP(regions, loss_type, loss_thresh)

loss_type = ['loss']
events['RP-year-loss'] = events['RP-year']
events_by_year = events.groupby(['RP-year-loss','year'])['loss'].sum().reset_index()
events_by_year.attrs['name'] = 'RAWOQ_GU_EQ_LOSS'
regions = [events_by_year]
plot_EP(regions, loss_type, loss_thresh)


#### Export regional and national RP data
east_RP.to_csv(str(insoutDir)+'/east_RP_Result_'+str(CALC_ID)+'.csv')
west_RP.to_csv(str(insoutDir)+'/west_RP_Result_'+str(CALC_ID)+'.csv')
national_RP.to_csv(str(insoutDir)+'/national_RP_Result_'+str(CALC_ID)+'.csv')

# west_RP.sort_values(by='RP-year-TotCostToIns', ascending=False).head(100).to_csv(str(insoutDir)+'/west_sample_RPresult_'+str(CALC_ID)+'.csv')




exit()
################## plotting losses by source zone, region to figure out why eastern losses are so high and why liq losses are so high for M9.1 CSZ
df = pd.concat([pd.read_csv(f) for f in glob.glob('./Summary_40_2026*.csv')], ignore_index=True)
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



