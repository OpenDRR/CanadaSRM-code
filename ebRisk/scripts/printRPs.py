# python function

##### NEED TO WORK THIS INTO A WHOLE SCRIPT, no time now. 

import numpy as np
import pandas as pd


#### PARAMETERS
insoutDir = '/Users/thobbs/Documents/CanadaSRM-output/probabilistic/current/ebRisk/ins-out'
CALC_ID = 43
RPs = np.array([100, 250, 500, 1000, 1250, 1650, 3300, 5000, 10000, 50000, 100000])
#### add a check to make sure RPs are not lower than RPmin = eff-time/N for N=number events/years(which?) and not higher than effective cat length.


#### LOAD DATA
events = pd.read_csv(str(insoutDir)+'/events_for_'+str(CALC_ID)+'.csv')
east_RP = pd.read_csv(str(insoutDir)+'/east_RP_Result_'+str(CALC_ID)+'.csv')
west_RP = pd.read_csv(str(insoutDir)+'/west_RP_Result_'+str(CALC_ID)+'.csv')
national_RP = pd.read_csv(str(insoutDir)+'/national_RP_Result_'+str(CALC_ID)+'.csv')



#### DEFINE FUNCTIONS
def interpolate_RP_losses(df, RPs, column):
    df = df.sort_values(column)
    colred = column.split('-')[2]
    
    return pd.DataFrame({
        'RP': RPs,
        colred: np.interp(
            np.log(RPs),
            np.log(df[column]),
            df[colred]
        )
    })


#### CALCULATE RP LOSSES AND SEND TO TABLE
rnding = 1000000000 #round to nearest 1 billion
cols = ['TotCostToIns','TotCostNotIns'] #must be 2 string entries, which represent uninsured and insured portion of total loss ('total loss' is calculated below by summing these).
tot = pd.DataFrame(RPs, columns=['RP']); k = 0
for d in [national_RP, east_RP, west_RP]: #must be national, east, west
    k += 1
    reg = pd.DataFrame(RPs, columns=['RP'])
    for val in cols:
        column = 'RP-year-'+val
        ins = interpolate_RP_losses(d, RPs, column)
        reg = reg.merge(ins)
    reg['TOT'] = reg[cols[0]] + reg[cols[1]] #add a total loss column
    reg = reg[['RP', 'TOT', cols[0], cols[1]]] #rearrange to match table
    if k == 2:
        tot = tot.merge(reg, on='RP', suffixes=('', '_EAST'))
    elif k == 3:
        tot = tot.merge(reg, on='RP', suffixes=('_NATL', '_WEST'))
    else:
        tot = tot.merge(reg, on='RP')

tot['RP'] = tot['RP']*rnding
print((tot/rnding).round(1).to_csv(index=False))
### copy paste output to MS word, highlight all, 'Insert > Table > Convert Text To Table'.











