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
oqIndir="/Users/thobbs/Documents/GitHub/canada-srm2/ebRisk/input/" 
oqOutdir="/Users/thobbs/Documents/CanadaSRM-output/probabilistic/current/ebRisk/oq-out"
iniFileName="ebRisk_b0_Canada_tinyInsuranceTest.ini" #"ebRisk_b0_Canada_Long_Expo2025_TestSmall.ini"
quants="False" #if True assumes quantiles of 0.05, 0.5, 0.95
insScript="/Users/thobbs/Documents/CanadaSRM-code/ebRisk/scripts/insuredProbLoss.py"
oqdataDir="/Users/thobbs/oqdata"

oqIndir="/work/CanadaSRM-code/ebRisk/input"
oqOutdir="/work/CanadaSRM-output/probabilistic/current/ebRisk/oq-out"
iniFileName="ebRisk_b0_Canada_Long_Expo2025_TestSmall.ini"
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

# Mount point of the EC2 instance NVMe filesystem
TMPDIR="/scratch"

# Where benchmark results will be stored
STATS_DIR="$TMPDIR/benchmark_stats" #!!!!!!! CHANGE TO EB
mkdir -p "$STATS_DIR"

INSTANCE_STATS="$STATS_DIR/instance.csv"
PROCESS_STATS="$STATS_DIR/process.csv"
IOSTAT_RAW="$STATS_DIR/iostat.raw"
SUMMARY="$STATS_DIR/summary.txt"

# Sampling interval in seconds
INTERVAL=5
START_TIME=$(date +%s)


# ============================================================
# CHECK REQUIRED COMMANDS
# ============================================================

for cmd in pidstat iostat mpstat free df awk ps pgrep; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: '$cmd' is not installed."
        echo
        echo "On Amazon Linux:"
        echo "    sudo dnf install sysstat"
        exit 1
    fi
done

### SETUP AWS KILL 
#set -E

#shut_down_ec2_instance() {
#    echo "Shutting down EC2 instance"
#    sudo shutdown -h now
#}

#trap shut_down_ec2_instance ERR


# ============================================================
# OUTPUT HEADERS
# ============================================================

echo "timestamp,cpu_pct,ram_used_gb,ram_pct,read_mb_s,write_mb_s,nvme_util_pct,tmp_used_gb,tmp_pct,inodes_pct" \
    > "$INSTANCE_STATS"

echo "timestamp,stage,cpu_pct,ram_gb,read_mb_s,write_mb_s" \
    > "$PROCESS_STATS"


# ============================================================
# FUNCTION: GET ALL DESCENDANT PIDS
#
# This recursively finds OpenQuake workers, Python workers,
# etc. spawned by the main process.
# ============================================================

get_descendants() {

    ROOT_PID="$1"

    PIDS="$ROOT_PID"
    CURRENT="$ROOT_PID"

    while [ -n "$CURRENT" ]; do

        NEXT=""

        for PID in $CURRENT; do

            CHILDREN=$(pgrep -P "$PID" 2>/dev/null)

            if [ -n "$CHILDREN" ]; then
                NEXT="$NEXT $CHILDREN"
                PIDS="$PIDS $CHILDREN"
            fi

        done

        CURRENT="$NEXT"

    done

    echo "$PIDS"
}


# ============================================================
# CONTINUOUS NVMe I/O MONITOR
#
# iostat stays running for the entire benchmark rather than
# being restarted every sampling interval.
# ============================================================

echo "Starting continuous iostat monitor..."

(
    iostat -dx "$INTERVAL" > "$IOSTAT_RAW"
) &

IOSTAT_PID=$!


# ============================================================
# WHOLE-INSTANCE MONITOR
# ============================================================

monitor_instance() {

    while true; do

        TIMESTAMP=$(date +%s)

        # ----------------------------------------------------
        # CPU
        # ----------------------------------------------------

        CPU=$(mpstat 1 1 |
            awk '/Average:/ && $2 == "all" {
                printf "%.2f", 100-$NF
            }')

        # ----------------------------------------------------
        # RAM
        # ----------------------------------------------------

        read RAM_USED RAM_PCT <<< $(free -m |
            awk '/Mem:/ {
                printf "%.2f %.2f", $3/1024, ($3/$2)*100
            }')

        # ----------------------------------------------------
        # NVMe storage usage
        # ----------------------------------------------------

        read TMP_USED TMP_PCT <<< $(df -BG "$TMPDIR" |
            awk 'NR==2 {
                gsub("G","",$3)
                gsub("%","",$5)
                printf "%.2f %.2f", $3, $5
            }')

        # ----------------------------------------------------
        # Inode usage
        # ----------------------------------------------------

        INODES=$(df -i "$TMPDIR" |
            awk 'NR==2 {
                gsub("%","",$5)
                printf "%.2f", $5
            }')

        # ----------------------------------------------------
        # Get most recent NVMe I/O measurement
        #
        # Sum all nvme devices.
        # ----------------------------------------------------

        read READ_MB WRITE_MB NVME_UTIL <<< $(

            awk '
            /^nvme[0-9]+n[0-9]+ / {
                read += $6
                write += $7
                util += $NF
                n++
            }

            END {
                if (n > 0)
                    printf "%.2f %.2f %.2f",
                        read,
                        write,
                        util/n
                else
                    printf "0 0 0"
            }' "$IOSTAT_RAW"

        )

        echo "$TIMESTAMP,$CPU,$RAM_USED,$RAM_PCT,$READ_MB,$WRITE_MB,$NVME_UTIL,$TMP_USED,$TMP_PCT,$INODES" \
            >> "$INSTANCE_STATS"

        sleep "$INTERVAL"

    done
}


# ============================================================
# PROCESS MONITOR
#
# Uses pidstat to monitor the entire process tree.
#
# A new pidstat process is started each interval so that newly
# spawned OpenQuake workers are included.
# ============================================================

monitor_process() {

    ROOT_PID="$1"
    STAGE="$2"

    while kill -0 "$ROOT_PID" 2>/dev/null; do

        TIMESTAMP=$(date +%s)

        PIDS=$(get_descendants "$ROOT_PID")

        # Convert spaces to commas for pidstat
        PID_LIST=$(echo "$PIDS" | tr ' ' ',')

        if [ -n "$PID_LIST" ]; then

            # CPU + memory + disk I/O
            #
            # -h = easier-to-parse output
            # -u = CPU
            # -r = memory
            # -d = I/O
            # -p = specific processes
            #
            pidstat -h -u -r -d -p "$PID_LIST" 1 1 2>/dev/null |
            awk -v timestamp="$TIMESTAMP" -v stage="$STAGE" '

            /^[0-9]/ {

                cpu = $8
                ram = $15 / 1024 / 1024
                read = $6 / 1024
                write = $7 / 1024

                total_cpu += cpu
                total_ram += ram
                total_read += read
                total_write += write

                n++

            }

            END {

                if (n > 0)
                    printf "%s,%s,%.2f,%.2f,%.2f,%.2f\n",
                        timestamp,
                        stage,
                        total_cpu,
                        total_ram,
                        total_read,
                        total_write

            }' >> "$PROCESS_STATS"

        fi

        sleep "$INTERVAL"

    done
}


# ============================================================
# START WHOLE-INSTANCE MONITOR
# ============================================================

monitor_instance &
INSTANCE_MONITOR_PID=$!


echo
echo "============================================================"
echo " OpenQuake benchmark started"
echo "============================================================"
echo " NVMe directory: $TMPDIR"
echo " Sampling interval: $INTERVAL seconds"
echo
echo " Raw statistics:"
echo "   $INSTANCE_STATS"
echo "   $PROCESS_STATS"
echo


# ============================================================
# OPENQUAKE CALCULATION
# ============================================================

echo "============================================================"
echo " Starting OpenQuake"
echo "============================================================"

### RUN RISK CALCS 
# could implement 'oq engine --run FILE --hc RUNNUM if useful
oq engine --run ${oqIndir}/${iniFileName} &> ${oqOutdir}/${prov}/ebR_${region}_oqlog.log;

OQ_PID=$!

echo "OpenQuake PID: $OQ_PID"

monitor_process "$OQ_PID" "OpenQuake" &
OQ_MONITOR_PID=$!

wait "$OQ_PID"

OQ_STATUS=$?

kill "$OQ_MONITOR_PID" 2>/dev/null
wait "$OQ_MONITOR_PID" 2>/dev/null


if [ "$OQ_STATUS" -ne 0 ]; then

    echo
    echo "ERROR: OpenQuake failed with exit status $OQ_STATUS"

    kill "$INSTANCE_MONITOR_PID" 2>/dev/null
    kill "$IOSTAT_PID" 2>/dev/null

    exit "$OQ_STATUS"

fi

echo
echo "OpenQuake completed successfully."


# ============================================================
# OPENQUAKE EXPORTS
# ============================================================

echo
echo "============================================================"
echo " Exporting OpenQuake outputs"
echo "============================================================"

# Replace this with your actual export command(s)

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


EXPORT_STATUS=$?

if [ "$EXPORT_STATUS" -ne 0 ]; then

    echo "ERROR: OpenQuake export failed."

    kill "$INSTANCE_MONITOR_PID" 2>/dev/null
    kill "$IOSTAT_PID" 2>/dev/null

    exit "$EXPORT_STATUS"

fi

echo "OpenQuake exports completed successfully."


# ============================================================
# CUSTOM PYTHON PARQUET PROCESSING
# ============================================================

echo
echo "============================================================"
echo " Starting custom Parquet processing"
echo "============================================================"

### RUN INS/2PER MODULE
python ${insScript} $CALC_ID ${oqIndir}/${iniFileName} $COMPUTE_RESOURCE &> ${oqOutdir}/${prov}/ebR_${region}_inslog.log;

PYTHON_PID=$!

echo "Python PID: $PYTHON_PID"

monitor_process "$PYTHON_PID" "Python_Parquet" &
PYTHON_MONITOR_PID=$!

wait "$PYTHON_PID"

PYTHON_STATUS=$?

kill "$PYTHON_MONITOR_PID" 2>/dev/null
wait "$PYTHON_MONITOR_PID" 2>/dev/null


if [ "$PYTHON_STATUS" -ne 0 ]; then

    echo
    echo "ERROR: Python processing failed."

    kill "$INSTANCE_MONITOR_PID" 2>/dev/null
    kill "$IOSTAT_PID" 2>/dev/null

    exit "$PYTHON_STATUS"

fi

echo
echo "Python processing completed successfully."


# ============================================================
# STOP MONITORING
# ============================================================

END_TIME=$(date +%s)

kill "$INSTANCE_MONITOR_PID" 2>/dev/null
kill "$IOSTAT_PID" 2>/dev/null

wait "$INSTANCE_MONITOR_PID" 2>/dev/null
wait "$IOSTAT_PID" 2>/dev/null

RUNTIME=$((END_TIME - START_TIME))


# ============================================================
# SUMMARIZE INSTANCE STATISTICS
# ============================================================

echo
echo "============================================================"
echo " Creating benchmark summary"
echo "============================================================"


awk -F',' '

NR > 1 {

    cpu_sum += $2
    ram_sum += $3

    if ($2 > cpu_max)
        cpu_max = $2

    if ($3 > ram_max)
        ram_max = $3

    if ($5 > read_max)
        read_max = $5

    if ($6 > write_max)
        write_max = $6

    if ($7 > io_max)
        io_max = $7

    if ($8 > tmp_max)
        tmp_max = $8

    if ($10 > inode_max)
        inode_max = $10

    n++
}

END {

    if (n == 0)
        exit

    printf "WHOLE EC2 INSTANCE\n"
    printf "------------------\n\n"

    printf "CPU:\n"
    printf "  Average utilization: %.1f %%\n", cpu_sum/n
    printf "  Peak utilization:    %.1f %%\n\n", cpu_max

    printf "RAM:\n"
    printf "  Average used:        %.1f GB\n", ram_sum/n
    printf "  Peak used:           %.1f GB\n\n", ram_max

    printf "NVMe I/O:\n"
    printf "  Peak read:           %.1f MB/s\n", read_max
    printf "  Peak write:          %.1f MB/s\n", write_max
    printf "  Peak utilization:    %.1f %%\n\n", io_max

    printf "Temporary storage:\n"
    printf "  Peak used:           %.1f GB\n", tmp_max
    printf "  Peak inode usage:    %.1f %%\n\n", inode_max

}' "$INSTANCE_STATS" > "$SUMMARY"


# ============================================================
# PROCESS STATISTICS
# ============================================================

echo "PROCESS-LEVEL STATISTICS" >> "$SUMMARY"
echo "-------------------------" >> "$SUMMARY"
echo >> "$SUMMARY"


for STAGE in OpenQuake Python_Parquet; do

    echo "$STAGE" >> "$SUMMARY"
    echo "------------------" >> "$SUMMARY"

    awk -F',' -v stage="$STAGE" '

    $2 == stage {

        cpu_sum += $3
        ram_sum += $4

        if ($3 > cpu_max)
            cpu_max = $3

        if ($4 > ram_max)
            ram_max = $4

        if ($5 > read_max)
            read_max = $5

        if ($6 > write_max)
            write_max = $6

        n++
    }

    END {

        if (n > 0) {

            printf "  Average CPU:       %.1f %%\n", cpu_sum/n
            printf "  Peak CPU:          %.1f %%\n", cpu_max

            printf "  Average RAM:       %.1f GB\n", ram_sum/n
            printf "  Peak RAM:          %.1f GB\n", ram_max

            printf "  Peak read:         %.1f MB/s\n", read_max
            printf "  Peak write:        %.1f MB/s\n", write_max

        } else {

            printf "  No measurements recorded.\n"

        }

        printf "\n"

    }' "$PROCESS_STATS" >> "$SUMMARY"

done


# ============================================================
# RUNTIME
# ============================================================

{

    echo "RUNTIME"
    echo "-------"

    printf "  Total runtime:      %02dh %02dm %02ds\n" \
        $((RUNTIME/3600)) \
        $(((RUNTIME%3600)/60)) \
        $((RUNTIME%60))

    echo

    echo "FILES"
    echo "-----"
    echo "  Summary:            $SUMMARY"
    echo "  Instance data:      $INSTANCE_STATS"
    echo "  Process data:       $PROCESS_STATS"
    echo "  Raw iostat:         $IOSTAT_RAW"

    echo
    echo "============================================================"

} >> "$SUMMARY"


# ============================================================
# DISPLAY SUMMARY
# ============================================================

cat "$SUMMARY"

echo
echo "Benchmark completed successfully."

### AWS KILL
#shut_down_ec2_instance
