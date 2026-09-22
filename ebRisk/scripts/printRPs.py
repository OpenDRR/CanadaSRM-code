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
expofile = '/Users/thobbs/Documents/CanadaSRM-input/current/exposure/oqBldgExp_CA_2025Update.csv'
expo = pd.read_csv(expofile)
RES = expo[expo['OccClass'].isin(['RES1', 'RES2'])]; RES.attrs['name'] = 'RES'
COM = expo[expo['OccClass'].isin(['RES3A', 'RES3C', 'RES3D', 'RES3B', 'RES3F', 'RES3E','RES3','RES4','RES5', 'RES6', 'COM1', 'COM2','COM3','COM4','COM5','COM6','COM7', 'COM8', 'COM9','COM10','IND1', 'IND2', 'IND3', 'IND4', 'IND5', 'IND6', 'AGR1', 'REL1'])]; COM.attrs['name'] = 'COM'
PUB = expo[~expo['OccClass'].isin(['RES1', 'RES2','RES3A', 'RES3C', 'RES3D', 'RES3B', 'RES3F', 'RES3E','RES3','RES4','RES5', 'RES6', 'COM1', 'COM2','COM3','COM4','COM5','COM6','COM7', 'COM8', 'COM9','COM10','IND1', 'IND2', 'IND3', 'IND4', 'IND5', 'IND6', 'AGR1', 'REL1'])]; PUB.attrs['name'] = 'PUB'
insParamFile="/Users/thobbs/Documents/CanadaSRM-code/ebRisk/scripts/InsParamsByFSA.csv"
ins_params = pd.read_csv(insParamFile)
RESparams = ins_params[ins_params['LoB'] == 'P']
COMparams = ins_params[ins_params['LoB'] == 'C']
provDict = expo[['pruid','prname']].drop_duplicates()

for k in [COM, RES]:
    LOB = k.attrs.get('name')
    for p in [35, 24, 59]:
        #35 = ON, 24 = QC, 59 = BC
        PROV = provDict[provDict['pruid'] == p]['prname'].values[0]
        df = k[k['pruid'] == p]
        if LOB == 'COM':
            params = COMparams
        else:
            params = RESparams
        
        df = df.merge(params[['FSA', 'EQDeducPerc', 'EQLimPerc', 'EQ_Pene']], how="left", left_on="fsauid", right_on="FSA").drop(columns='FSA')
        df['totalVal'] = df['structural']+df['nonstructural']+df['contents']
        df['rando'] = np.random.rand(len(df))
        df['ins_val'] = df['totalVal'].where(df['rando'] < df['EQ_Pene'], 0)
        print('Insured asset total for '+str(LOB)+' LoB in '+str(PROV)+' is $'+str(df['ins_val'].sum()/1e9)+' billion CAD.')
        del df

#For CatIQ vals see the InsParams_from_CatIQ script, at end.











