#!/bin/bash

# ==========================================================================
# Script for running ebRisk calculations in the National Canadian Risk Model
# ==========================================================================
usage() {
echo "Script for running ebRisk calculations in OpenQuake, using Canadian data, and implementing the Insurance / Secondary Peril module. 
You need to have created the ini files already. Originally written by TE Hobbs on 3 Aug 2021, updated summer 2026. 


USAGE: bash ../../../../CanadaSRM-code/scenario/scripts/run_OQscenRisk_Ins.sh
    to be run from the CanadaSRM-output/deterministic/current/ folder. Runs only b0.

"
}

# ============================================================
# CONFIGURATION
# ============================================================

### USER: DEFINE CALCULATIONS AND FOLDERS

iniFileName="s_Risk_SIM9p1_CascadiaInterfaceBestFault_b0_b.ini"

oqIndir="/work/CanadaSRM-code/scenario/input"
outDir="/work/CanadaSRM-output/deterministic/current"
oqOutdir="${outDir}/oq-out"
scriptDir="/work/CanadaSRM-code/scenario/scripts"
insScript="${scriptDir}/insuredDetLoss.py"
oqdataDir="/home/ssm-user/oqdata"
quants="False" #if True assumes quantiles of 0.05, 0.5, 0.95
COMPUTE_RESOURCE="AWS" #THlaptop

### INITIALIZE PARAMS, FOLDERS
calc="b0"; calcnum="-1"
mkdir -p ${outDir}/temp; rm -f ${outDir}/temp/*
mkdir -p ${oqOutdir}
basename=$(echo $iniFileName | awk -F'_' '{print $3"_"$4}')

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
oq engine --run ${oqIndir}/${iniFileName} &> ${oqOutdir}/latest_oqlog.log;


echo "OpenQuake completed successfully."

echo "============================================================"
echo " Exporting OpenQuake outputs"
echo "============================================================"

### STANDARD OQ EXPORTS and GET CALC ID
oq export avg_losses-stats -1 -e csv -d ${outDir}/temp
CALC_ID=$(ls -t ${outDir}/temp/avg_losses* | head -1 | awk -F'[_.]' '{print $(NF-1)}')
cp ${outDir}/temp/avg_losses-mean_${CALC_ID}.csv ${oqOutdir}/avg_losses-mean_${basename}.csv


### COPY oq_data to EBS
cp ${oqdataDir}/calc_${CALC_ID}.hdf5 ${oqOutdir}/


echo "OpenQuake exports completed successfully."

echo "============================================================"
echo " Starting custom Parquet processing"
echo "============================================================"

### RUN INS/2PER MODULE
python insScript $CALC_ID ${oqIndir}/${iniFileName} $COMPUTE_RESOURCE

echo "Python processing completed successfully."



### AWS KILL
shut_down_ec2_instance
