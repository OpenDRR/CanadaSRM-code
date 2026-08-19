# Python script to export the augmented calculation event table for post-processing of probabilistic insurance module run. Written by TEH in Aug 2026 while she was very very eepy. 


#### Imports
from openquake.commonlib.datastore import read
import pandas as pd


#### Configuration
CALC_ID=34
outDir = '/work/CanadaSRM-output/probabilistic/current/ebRisk/ins-out'
eff_time = 500000


#### Load Data
dstore = read(CALC_ID)


#### Get standard export 'loss by event' table
loss_by_event = dstore.read_df('risk_by_event')
lbe = loss_by_event[['event_id','loss']].groupby(['event_id'], as_index=False).sum() #sum over diff loss types


#### Get source model information for each event & merge them
rups = dstore.read_df('ruptures') #read oq ruptures
sources = dstore.read_df('source_info'); sources = sources.reset_index() #read oq sources
events = dstore.read_df('events') #read oq events
events = events.merge(rups[['id', 'source_id', 'mag', 'occurrence_rate']], left_on='rup_id', right_on='id', how='left', suffixes=('','_rup')) #add rupture id from rupture df
events['source_name'] = sources.iloc[events["source_id"]].reset_index(drop=True)['source_id'] #grab source name from sources df, based on rupture id
events['source_name'] = events['source_name'].str.decode("utf-8") #decode


#### Find RP for each effective year, assign to events
# based on https://docs.openquake.org/oq-engine/manual/latest/user-guide/outputs/event-based-risk-outputs.html#:~:text=computes%20the%20Probably,eff_time%20is%20respected. 
events = events.merge(lbe, how = "left", left_on = "id", right_on = "event_id").fillna(0).drop(columns="event_id")
ranked_loss = events.groupby('year')['loss'].sum().sort_values(ascending=False).reset_index()
ranked_loss['RP-year'] = eff_time/((ranked_loss.index)+1)
events = events.merge(ranked_loss[['year','RP-year']], on='year', how='left')


#### Export csv
events.to_csv(str(outDir)+'/events_for_'+str(CALC_ID)+'.csv')