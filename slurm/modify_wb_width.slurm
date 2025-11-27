#!/bin/bash
#SBATCH --job-name=modify_wb_width
#SBATCH --output=slurm_logs/modify_wb_width_%j.out
#SBATCH --error=slurm_logs/modify_wb_width_%j.err

FILE_PATH="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/configs/mast/profile-config-legacy.py"
# Capture the command-line arguments passed to the script
WB_WIDTH=$1

# Check if both arguments were provided
if [ -z "$WB_WIDTH" ]; then
    echo "Error: WB_WIDTH must be provided as argument."
    echo "Usage: sbatch modify_wb_width.slurm <WB_WIDTH_VALUE>"
    exit 1
fi

echo "Modifying files with:"
echo "WB_WIDTH: ${WB_WIDTH}"

# Modify the two lines using the values from the arguments
sed -i "125s/.*/        cpu.wbWidth = ${WB_WIDTH}/" "${FILE_PATH}"

echo "File modifications complete."

sed -n "125p" "${FILE_PATH}"
