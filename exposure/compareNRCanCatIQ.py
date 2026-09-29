#!/bin/python

#### Python script to calculate the exposure from NRCan and CatIQ, for total exposure and quake-only exposure. Values should be for eastern, western, and national. Should include ALE/BI at least for quake - SPECIFY THIS WHEN GIVING RESULTS.
# To be run on laptop


#### Import statements
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


#### User-specified filepaths and parameters
expofile = '/Users/thobbs/Documents/CanadaSRM-input/current/exposure/oqBldgExp_CA_2025Update.csv'
insParamFile = "/Users/thobbs/Documents/CanadaSRM-code/ebRisk/scripts/InsParamsByFSA.csv"
catIQfile = '/Users/thobbs/Documents/CanadaSRM-code/ebRisk/scripts/CatIQExpoDF.csv'


#### Load expo data and assign region by P/T, LoB
expo = pd.read_csv(expofile)
expo['totalVal'] = expo['structural']+expo['nonstructural']+expo['contents']
#provDict = expo[['pruid','prname']].drop_duplicates() #dict of P/Ts by name and id
Eprovs = [46, 13, 12, 62, 35, 11, 24, 10] #MB, NU, ON, QC, Martms
Wprovs = [59, 48, 61, 47, 60] #BC, AB, SK, YT, NT in no order
expo['region'] = np.select([expo["pruid"].isin(Eprovs), expo["pruid"].isin(Wprovs)], ['East', 'West'], default=np.nan)
expo['LoB'] = np.select([expo['OccClass'].isin(['RES1', 'RES2']), expo['OccClass'].isin(['RES3A', 'RES3C', 'RES3D', 'RES3B', 'RES3F', 'RES3E', 'RES3', 'RES4', 'RES5', 'RES6', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'COM10', 'IND1', 'IND2', 'IND3', 'IND4', 'IND5', 'IND6', 'AGR1', 'REL1'])], ['P','C'], default='O')


#### Load insurance data and add to expo by FSA and LoB
ins_params = pd.read_csv(insParamFile)
expo['FSA'] = expo['fsauid']
expo = expo.merge(ins_params[['FSA', 'LoB', 'EQDeducPerc', 'EQ_Pene', 'EQLimPerc']], on=['FSA', 'LoB'], how='left', validate='many_to_one').fillna(0)


#### Add insured value
expo['rando'] = np.random.rand(len(expo))
expo['ins_val'] = expo['totalVal'].where(expo['rando'] < expo['EQ_Pene'], 0)


#### Group NRCan expo by region / natl and LoB
expo = expo.rename(columns={"ins_val": "QUAKE", "totalVal": "TOTAL"})
grouped = expo.groupby(['region','LoB'])[['QUAKE','TOTAL']].sum().reset_index()
tots = expo.groupby(['LoB'])[['QUAKE','TOTAL']].sum().reset_index()
nrcanout = pd.concat([grouped, tots]).fillna('National')


#### Load CatIQ vals and group by region / natl and LoB
catiq = pd.read_csv(catIQfile)
regs = expo.groupby('FSA')['region'].agg(set).reset_index()
regs['region'] = regs['region'].apply(
    lambda x: next(iter(x)) if len(x) == 1 else None
) # lambda ensures there's only one region per FSA
catiq = catiq.merge(regs, on='FSA', how='left')
catiq = catiq.rename(columns={"BldgContVal_EQ": "QUAKE", "maxBldgContVal": "TOTAL"})
catgrouped = catiq.groupby(['region','LoB'])[['QUAKE','TOTAL']].sum().reset_index()
cattots = catiq.groupby(['LoB'])[['QUAKE','TOTAL']].sum().reset_index()
catout = pd.concat([catgrouped, cattots]).fillna('National')
catout = pd.concat([catout, pd.DataFrame([{'region':'East', 'LoB':'O', 'QUAKE': 0.0, 'TOTAL': 0.0}])])
catout = pd.concat([catout, pd.DataFrame([{'region':'West', 'LoB':'O', 'QUAKE': 0.0, 'TOTAL': 0.0}])])
catout = pd.concat([catout, pd.DataFrame([{'region':'National', 'LoB':'O', 'QUAKE': 0.0, 'TOTAL': 0.0}])])


#### Spit out results in a table and figures
nrcanout['source'] = 'NRCan'; catout['source'] = 'CatIQ'
outdf = pd.concat([nrcanout, catout])
outdf['QUAKE'] /= 1e12; outdf['TOTAL'] /= 1e12 #make trillions CAD


#### Plot settings
regions = ['East', 'West', 'National']; lobs = ['P', 'C', 'O']; sources = ['NRCan', 'CatIQ']; metrics = ['QUAKE', 'TOTAL']
colors = {('P', 'NRCan'): '#C65D00',   # dark orange
    ('P', 'CatIQ'): '#F4A261',   # light orange
    ('C', 'NRCan'): '#2166AC',   # dark blue
    ('C', 'CatIQ'): '#67A9CF',   # light blue
    ('O', 'NRCan'): '#63666A',   # dark grey
    ('O', 'CatIQ'): '#B0B0B0'}   # light grey
n_bars = len(lobs) * len(sources); bar_width = 0.18; x = np.arange(len(regions))


#### Plot
fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True, constrained_layout=True)

for ax, metric in zip(axes, metrics):
    for i, lob in enumerate(lobs):
        for j, source in enumerate(sources):
            offset = ((i * len(sources) + j) - (n_bars - 1) / 2) * bar_width
            values = []
            for region in regions:
                match = outdf[(outdf['region'] == region) & (outdf['LoB'] == lob) & (outdf['source'] == source)]
                values.append(match[metric].iloc[0] if len(match) else 0)
            
            #ax.bar(x + offset, values, width=bar_width, color=colors[(lob, source)], edgecolor='black', linewidth=0.5)
            bars = ax.bar(x + offset, values, width=bar_width, color=colors[(lob, source)], edgecolor='black', linewidth=0.5)
            ax.bar_label(bars, labels=[f'${v:.1f}T' for v in values], padding=3, fontsize=8)
    
    ax.set_ylabel(f'{metric} ($ trillions)')
    ax.grid(axis='y', linestyle=':', alpha=0.5)
    ax.set_axisbelow(True)
    ymax = ax.get_ylim()[1]
    ax.set_ylim(0, ymax * 1.08)

axes[-1].set_xticks(x)
axes[-1].set_xticklabels(regions)
axes[-1].set_xlabel('Region')
#axes[0].set_title('Earthquake insurance losses')

legend_elements = [
    Patch(facecolor=colors[('P', 'NRCan')], edgecolor='black', label='NRCan (P)'),
    Patch(facecolor=colors[('P', 'CatIQ')], edgecolor='black', label='CatIQ (P)'),
    Patch(facecolor=colors[('C', 'NRCan')], edgecolor='black', label='NRCan (C)'),
    Patch(facecolor=colors[('C', 'CatIQ')], edgecolor='black', label='CatIQ (C)'),
    Patch(facecolor=colors[('O', 'NRCan')], edgecolor='black', label='NRCan (O)'),
    Patch(facecolor=colors[('O', 'CatIQ')], edgecolor='black', label='CatIQ (O)')]

#fig.legend(handles=legend_elements, loc='upper center', ncol=6, frameon=False) #, bbox_to_anchor=(0.5, 1.02)
axes[0].legend(handles=legend_elements, loc='upper center', frameon=True, ncol=6)

plt.show()

####### TO DO:
# Add BI/ALE?











