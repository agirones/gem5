#!/bin/bash
#SBATCH --job-name=modify_code
#SBATCH --output=slurm_logs/modify_code_%j.out
#SBATCH --error=slurm_logs/modify_code_%j.err

FILE_PATH="src/cpu/o3/iew.cc"
# Capture the command-line arguments passed to the script
# $1 will be the value for MAX_BROADCASTS
# $2 will be the value for MAX_POINTERS
MAX_BROADCASTS=$1
MAX_POINTERS=$2
BASE_DIR=$3

# Check if both arguments were provided
if [ -z "$MAX_BROADCASTS" ] || [ -z "$MAX_POINTERS" ]; then
    echo "Error: Both MAX_BROADCASTS and MAX_POINTERS must be provided as arguments."
    echo "Usage: sbatch modify_file.slurm <MAX_BROADCASTS_VALUE> <MAX_POINTERS_VALUE>"
    exit 1
fi

if [ -z "$BASE_DIR" ]; then
    echo "Warning: No base directory provided, using default"
    BASE_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/"
fi

FILE_PATH="${BASE_DIR}${FILE_PATH}"

echo "Modifying files with:"
echo "MAX_BROADCASTS: ${MAX_BROADCASTS}"
echo "MAX_POINTERS: ${MAX_POINTERS}"

# Modify the two lines using the values from the arguments
sed -i "1966s/.*/    const int dependentsThreshold = ${MAX_POINTERS};/" "${FILE_PATH}"
sed -i "2076s/.*/    const int broadcastMax = ${MAX_BROADCASTS};/" "${FILE_PATH}"

echo "File modifications complete."

sed -n "1966p;2076p" "${FILE_PATH}"
