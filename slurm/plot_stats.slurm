#!/bin/bash
#SBATCH --job-name=plot_stats
#SBATCH --output=slurm_logs/plot_stats_%A_%a.out
#SBATCH --error=slurm_logs/plot_stats_%A_%a.err
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=8GB
#SBATCH --array=1-8

ROOT_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU"
if [ -z "$OUTPUT_DIR" ]; then
    OUTPUT_DIR="$PWD"
fi
PLOT_SCRIPT_PATH="runs/scripts/plot_stats.py"
CPU_WIDTH=$SLURM_ARRAY_TASK_ID

echo "BASE_DIR: $OUTPUT_DIR"

module load SciPy-bundle/2024.05-gfbf-2024a
module load matplotlib/3.9.2-gfbf-2024a

echo "Running plotting script for CPU width $CPU_WIDTH..."
python3 "$ROOT_DIR/$PLOT_SCRIPT_PATH" --base-dir "$OUTPUT_DIR/width$CPU_WIDTH"
