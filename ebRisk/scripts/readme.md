# ReadMe for CanadaSRM-code/ebRisk/scripts

This folder contains scripts used to support ebRisk calculations:
- **event_based_risk_exportParq_backup.py**: A copy of the OQ ebrisk calculator script for the insurance module, stored locally in /Users/thobbs/oq-engine/openquake/calculators. It has been modified to export parquets for each asset for each event. It requires the following python modules: os, uuid, pathlib, pyarrow, datetime. You must modify the export directory to match your local file structure.
- **event_based_risk_backup.py**: A copy of the unedited OQ ebrisk calculator script. 
