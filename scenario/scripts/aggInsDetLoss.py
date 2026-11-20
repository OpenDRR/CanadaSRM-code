#python script to output scenario results using 'summary' files
import pandas as pd
pd.options.display.float_format = '{:.1f}'.format

calc_df = pd.DataFrame([
    {'CALC_ID': 32, 'filename': "/Users/thobbs/Documents/CanadaSRM-output/deterministic/current/ins-out/Summary_32.csv", 'scen_name': 'M5p8_Montreal'},
    {'CALC_ID': 30, 'filename': "/Users/thobbs/Documents/CanadaSRM-output/deterministic/current/ins-out/Summary_30.csv", 'scen_name': 'M7p5_Montreal'},
    {'CALC_ID': 41, 'filename': "/Users/thobbs/Documents/CanadaSRM-output/deterministic/current/ins-out/Summary_41.csv", 'scen_name': 'M9p1_Cascadia'},
    {'CALC_ID': 28, 'filename': "/Users/thobbs/Documents/CanadaSRM-output/deterministic/current/ins-out/Summary_28.csv", 'scen_name': 'M9p2_Cascadia'},
    {'CALC_ID': 33, 'filename': "/Users/thobbs/Documents/CanadaSRM-output/deterministic/current/ins-out/Summary_33.csv", 'scen_name': 'M7p0_GeorgiaStraitAshock'}
])

df = pd.concat([
    pd.read_csv(row.filename).assign(
        CALC_ID=row.CALC_ID,
        scen_name=row.scen_name
    )
    for row in calc_df.itertuples()
], ignore_index=True)

df['scen_name']
df[['GU_EQOnly_loss', 'ins_EQLQ_loss', 'PH_EQLQ_loss', 'UI_EQLQ_loss', 'auto_EQLQ_loss', 'FFE_loss', 'tot_tsunami', 'TotCost_EQLQAutoSecPerils', 'TotCostToIns']]/1e9

print('combo M9.2+ashock')
df2 = pd.concat([df[df['scen_name'] == 'M9p2_Cascadia'], df[df['scen_name'] == 'M7p0_GeorgiaStraitAshock']])
df2.loc[len(df)] = df2.select_dtypes(include='number').sum()
df2.tail(1)[['GU_EQOnly_loss', 'ins_EQLQ_loss', 'PH_EQLQ_loss', 'UI_EQLQ_loss', 'auto_EQLQ_loss', 'FFE_loss', 'tot_tsunami', 'TotCost_EQLQAutoSecPerils', 'TotCostToIns']]/1e9