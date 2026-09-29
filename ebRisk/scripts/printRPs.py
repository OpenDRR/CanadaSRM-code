# python function

##### NEED TO WORK THIS INTO A WHOLE SCRIPT, no time now. 

import numpy as np
import pandas as pd


#### PARAMETERS
insoutDir = '/Users/thobbs/Documents/CanadaSRM-output/probabilistic/current/ebRisk/ins-out'
CALC_ID = 40
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
column = 'RP-year-TotCostToIns'
column = 'RP-year-TotCostNotIns'
national_interp = interpolate_RP_losses(national_RP, RPs, column)




###################################
#TO DOs FROM PSY - ALL DONE
#- addtl RPs at 1250, 1650, 3300
#- separate east west ep curves and tables in the doc
#- eq-insured asset base for BC, ON, QC, broken down by LOB.












