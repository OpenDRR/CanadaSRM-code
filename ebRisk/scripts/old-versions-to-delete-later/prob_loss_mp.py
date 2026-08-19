#!/usr/bin/env python3
from multiprocessing import Pool
import os
import glob
import pyarrow.csv as pv
import pyarrow.parquet as pq
from pathlib import Path

def processFile(filePath):
    print("Started processing file: " + filePath)

    # load the parquet file
    table = pq.read_table(filePath)

    # Get only the filename
    parquetFileName = Path(filePath).name

    pv.write_csv(table, os.getcwd() + "/canada/insuredProbLossOutput/" + parquetFileName)

    print("Finsihed processing file: " + filePath)

    return

def main() -> int:
    numProcs = os.cpu_count()

    cwd = os.getcwd()

    parquetFiles = glob.glob(cwd + "/canada/ins-out/*.parquet")

    # Create output file if not exists
    Path(cwd + "/canada/insuredProbLossOutput/").mkdir(parents=True, exist_ok=False)

    with Pool(processes=numProcs) as pool:
        for parquetFile in parquetFiles:
            pool.apply_async(processFile, (parquetFile,))

        pool.close()
        pool.join()

    print("Processing has finished")

    return 0

if __name__ == "__main__":
    main()