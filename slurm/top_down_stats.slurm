#!/bin/bash
#SBATCH --job-name=top_down_stats
#SBATCH --output=slurm_logs/top_down_stats_%A_%a.out
#SBATCH --error=slurm_logs/top_down_stats_%A_%a.err
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=8GB
#SBATCH --array=1-8

OUTPUT_DIR=$PWD
ROOT_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU"
TOP_DOWN_SCRIPT_PATH="$ROOT_DIR/runs/scripts/top_down_stats.py"
TOP_DOWN_OUTPUT_PATH="$OUTPUT_DIR/top_down_data.csv"
CPU_WIDTH=$SLURM_ARRAY_TASK_ID

module load SciPy-bundle/2024.05-gfbf-2024a
module load matplotlib/3.9.2-gfbf-2024a
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/
rm $TOP_DOWN_OUTPUT_PATH

echo "Running top_down script for CPU width $CPU_WIDTH..."
python3 $TOP_DOWN_SCRIPT_PATH --base-dir $OUTPUT_DIR/width$CPU_WIDTH \
    --output-dir "$TOP_DOWN_OUTPUT_PATH"
