# Python script to aggregate insProbLoss output csv's and create RP curves/files. Written by TEH in Aug 2026.

import glob
import pandas as pd
import re
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter, LogLocator

#### Configuration - USER SPECIFIED
CALC_ID = 31
INI_FILENAME = "/Users/thobbs/Documents/CanadaSRM-code/ebRisk/input/ebRisk_b0_Canada_500kyr_Expo2025.ini"
insoutDir = '/Users/thobbs/Documents/CanadaSRM-output/probabilistic/current/ebRisk/ins-out'

###################### NEED TO FIX BELOW TO DO YEAR NOT EVENT
#### Define RP function
# Based on 'eid', assumes all events from catalogue are in 'data'.
def get_RP(data, eff_time, loss_type):
    ilbe = data[['eid',str(loss_type)]].sort_values(str(loss_type), ascending=False).reset_index()
    outcolname = 'RP_'+str(loss_type)
    ilbe[outcolname] = eff_time/((ilbe.index)+1)
    outdf = data.merge(ilbe[['eid',outcolname]], how='left', on='eid')
    outdf = outdf.sort_values(by=outcolname)
    return outdf


#### Define plotting function
def plot_EP(east, west, national, loss_type):
    fig, ax = plt.subplots(figsize=(10, 7))
    # Plot the three datasets
    ax.plot(east['RP_'+str(loss_type)], east[str(loss_type)] / 1e9, marker="o", label="East")
    ax.plot(west['RP_'+str(loss_type)], west[str(loss_type)] / 1e9, marker="o", label="West")
    ax.plot(national['RP_'+str(loss_type)], national[str(loss_type)] / 1e9, marker="o", label="National")
    # Log-log axes
    ax.set_xscale("log"); ax.set_yscale("log")
    # Axis labels
    ax.set_xlabel("Return Period [years]", fontsize=12)
    ax.set_ylabel(str(loss_type)+" [billions of dollars]", fontsize=12)
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
    plt.show()
    plt.savefig(insoutDir+'/Result_'+str(CALC_ID)+'.png')


#### Read csvs
df = pd.concat([pd.read_csv(f) for f in glob.glob(str(insoutDir) + '/Summary_' + str(CALC_ID) + '_*.csv')], ignore_index=True)


#### Get/calculate the effective calculation time
number_of_logic_tree_samples, ses_per_logic_tree_path, investigation_time = [int(re.search(r'=\s*(\d+)', l).group(1)) for l in open(INI_FILENAME) if l.startswith(("number_of_logic_tree_samples", "ses_per_logic_tree_path", "investigation_time"))]
eff_time = number_of_logic_tree_samples * ses_per_logic_tree_path * investigation_time


#### Isolate east, west, natl
# Only keep useful columns
east = df[df['ss_region'] == 1][['eid', "eff_year", "RP_EQ-effyear",'mag','occ_rate', 'GU_EQOnly_loss', 'GU_LQOnly_loss', 'GU_EQLQ_loss', 'ins_EQLQ_loss', 'PH_EQLQ_loss', 'UI_EQLQ_loss', 'auto_EQLQ_loss', 'EQLQTotal', 'FFE_loss', 'tot_tsunami', 'ins_tsunami', 'TotCostToIns']]
west = df[df['ss_region'] == 2][['eid',"eff_year", "RP_EQ-effyear",'mag','occ_rate', 'GU_EQOnly_loss', 'GU_LQOnly_loss', 'GU_EQLQ_loss', 'ins_EQLQ_loss', 'PH_EQLQ_loss', 'UI_EQLQ_loss', 'auto_EQLQ_loss', 'EQLQTotal', 'FFE_loss', 'tot_tsunami', 'ins_tsunami', 'TotCostToIns']]
national = df[['eid',"eff_year", "RP_EQ-effyear",'mag','occ_rate', 'GU_EQOnly_loss', 'GU_LQOnly_loss', 'GU_EQLQ_loss', 'ins_EQLQ_loss', 'PH_EQLQ_loss', 'UI_EQLQ_loss', 'auto_EQLQ_loss', 'EQLQTotal', 'FFE_loss', 'tot_tsunami', 'ins_tsunami', 'TotCostToIns']].groupby(['eid',"eff_year", "RP_EQ-effyear",'mag','occ_rate'], as_index=False).sum() #combine east and west


#### Get insured RPs and plot
loss_type = 'TotCostToIns'
east = get_RP(east, eff_time, loss_type)
west = get_RP(west, eff_time, loss_type)
national = get_RP(national, eff_time, loss_type)
plot_EP(east, west, national, loss_type)


#### Export regional and national data
east.to_csv(str(insoutDir)+'/east_result_'+str(CAL_ID)+'.csv')
west.to_csv(str(insoutDir)+'/west_result_'+str(CAL_ID)+'.csv')
national.to_csv(str(insoutDir)+'/national_result_'+str(CAL_ID)+'.csv')








