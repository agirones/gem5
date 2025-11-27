#!/bin/bash
#SBATCH --job-name=modify_max_broadcasts
#SBATCH --output=slurm_logs/modify_max_broadcasts_%j.out
#SBATCH --error=slurm_logs/modify_max_broadcasts_%j.err

FILE_PATH="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/src/cpu/o3/iew.cc"
# Capture the command-line arguments passed to the script
# $1 will be the value for MAX_BROADCASTS
# $2 will be the value for MAX_POINTERS
MAX_BROADCASTS=$1

# Check if both arguments were provided
if [ -z "$MAX_BROADCASTS" ]; then
    echo "Error: MAX_BROADCASTS must be provided as argument."
    echo "Usage: sbatch modify_max_broadcasts.slurm <MAX_BROADCASTS_VALUE>"
    exit 1
fi

echo "Modifying files with:"
echo "MAX_BROADCASTS: ${MAX_BROADCASTS}"

# Modify the two lines using the values from the arguments
sed -i "2027s/.*/    const int broadcastMax = ${MAX_BROADCASTS};/" "${FILE_PATH}"

echo "File modifications complete."

sed -n "2027p" "${FILE_PATH}"
