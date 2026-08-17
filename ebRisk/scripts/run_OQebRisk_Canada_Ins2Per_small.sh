#!/bin/bash

# ==========================================================================
# Script for running ebRisk calculations in the National Canadian Risk Model
# ==========================================================================
usage() {
echo "Script for running ebRisk calculations in OpenQuake, using Canadian data, and implementing the Insurance / Secondary Peril module. 
You need to have created the ini files already. Originally written by TE Hobbs on 3 Aug 2021, updated summer 2026. 


USAGE: bash ../../../../CanadaSRM-code/ebRisk/scripts/run_OQebRisk_Canada_Ins2Per.sh
    to be run from the CanadaSRM-output/probabilistic/current/ebRisk/ folder. Runs only b0.

"
}

# ============================================================
# CONFIGURATION
# ============================================================

### USER: DEFINE CALCULATIONS AND FOLDERS
oqIndir="/Users/thobbs/Documents/GitHub/canada-srm2/ebRisk/input" 
oqOutdir="/Users/thobbs/Documents/CanadaSRM-output/probabilistic/current/ebRisk/oq-out"
iniFileName="ebRisk_b0_Canada_tinyInsuranceTest.ini" #"ebRisk_b0_Canada_Long_Expo2025_TestSmall.ini"
quants="False" #if True assumes quantiles of 0.05, 0.5, 0.95
insScript="/Users/thobbs/Documents/CanadaSRM-code/ebRisk/scripts/insuredProbLoss.py"
oqdataDir="/Users/thobbs/oqdata"

oqIndir="/work/CanadaSRM-code/ebRisk/input"
oqOutdir="/work/CanadaSRM-output/probabilistic/current/ebRisk/oq-out"
iniFileName="ebRisk_b0_Canada_Long_Expo2025.ini"
quants="False"
insScript="/work/CanadaSRM-code/ebRisk/scripts/insuredProbLoss.py"
oqdataDir="/home/ssm-user/oqdata"

COMPUTE_RESOURCE="AWS" #THlaptop

### INITIALIZE PARAMS, FOLDERS
region="Canada"
calc="b0"; calcnum="-1"
mkdir -p ${oqOutdir}/temp; rm -f ${oqOutdir}/temp/*
prov=$region
mkdir -p ${oqOutdir}/${prov}

### SETUP AWS KILL
set -E

shut_down_ec2_instance() {
    echo "Shutting down EC2 instance"
    sudo shutdown -h now
    }

trap shut_down_ec2_instance ERR


echo "============================================================"
echo " Starting OpenQuake"
echo "============================================================"

### RUN RISK CALCS
# could implement 'oq engine --run FILE --hc RUNNUM if useful
oq engine --run ${oqIndir}/${iniFileName} &> ${oqOutdir}/${prov}/ebR_${region}_oqlog.log;


echo "OpenQuake completed successfully."

echo "============================================================"
echo " Exporting OpenQuake outputs"
echo "============================================================"

### STANDARD OQ EXPORTS and GET CALC ID
oq export fullreport $calcnum -e rst -d ${oqOutdir}/temp/
file=$(printf '%s\n' ${oqOutdir}/temp/report_*.rst)
num=${file##*/report_}
CALC_ID=${num%.rst} #collect the calculation number
mv ${oqOutdir}/temp/report*.rst ${oqOutdir}/${prov}/ebR_${region}_report_${calc}.csv
oq export realizations $calcnum -e csv -d ${oqOutdir}/temp/
mv ${oqOutdir}/temp/realizations*.csv ${oqOutdir}/${prov}/ebR_${region}_rlz_b0.csv

if [[ "$quants" == "True" ]]; then
    oq export agg_curves-stats $calcnum -e csv -d ${oqOutdir}/temp/
    mv ${oqOutdir}/temp/agg_curves-mean*.csv ${oqOutdir}/${prov}/ebR_${region}_agg_curves-stats_${calc}.csv;
    mv ${oqOutdir}/temp/agg_curves-quantile-0.05*.csv ${oqOutdir}/${prov}/ebR_${region}_agg_curves-q05_${calc}.csv;
    mv ${oqOutdir}/temp/agg_curves-quantile-0.5*.csv ${oqOutdir}/${prov}/ebR_${region}_agg_curves-q50_${calc}.csv;
    mv ${oqOutdir}/temp/agg_curves-quantile-0.95*.csv ${oqOutdir}/${prov}/ebR_${region}_agg_curves-q95_${calc}.csv;
    oq export agg_losses-stats $calcnum -e csv -d ${oqOutdir}/temp/
    mv ${oqOutdir}/temp/agg_losses-mean*.csv ${oqOutdir}/${prov}/ebR_${region}_agg_losses-stats_${calc}.csv;
    mv ${oqOutdir}/temp/agg_losses-quantile-0.05*.csv ${oqOutdir}/${prov}/ebR_${region}_agg_losses-q05_${calc}.csv;
    mv ${oqOutdir}/temp/agg_losses-quantile-0.5*.csv ${oqOutdir}/${prov}/ebR_${region}_agg_losses-q50_${calc}.csv;
    mv ${oqOutdir}/temp/agg_losses-quantile-0.95*.csv ${oqOutdir}/${prov}/ebR_${region}_agg_losses-q95_${calc}.csv;
    oq export src_loss_table $calcnum -e csv -d ${oqOutdir}/temp/
    mv ${oqOutdir}/temp/src_loss_table_*.csv ${oqOutdir}/${prov}/ebR_${region}_src_loss_table_${calc}.csv;
else
    oq export aggcurves $calcnum -e csv -d ${oqOutdir}/temp/
    mv ${oqOutdir}/temp/aggcurves-*.csv ${oqOutdir}/${prov}/ebR_${region}_aggcurves-_${calc}.csv;
fi


### COPY oq_data to EBS
cp ${oqdataDir}/calc_${CALC_ID}.hdf5 ${oqOutdir}/${prov}/calc_${CALC_ID}.hdf5


echo "OpenQuake exports completed successfully."

echo "============================================================"
echo " Starting custom Parquet processing"
echo "============================================================"

### RUN INS/2PER MODULE
python ${insScript} $CALC_ID ${oqIndir}/${iniFileName} $COMPUTE_RESOURCE &> ${oqOutdir}/${prov}/ebR_${region}_inslog.log;

echo "Python processing completed successfully."



### AWS KILL
shut_down_ec2_instance
