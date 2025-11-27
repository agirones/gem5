#!/bin/bash
#SBATCH --job-name=bottleneck_stats
#SBATCH --output=slurm_logs/bottleneck_stats_%A_%a.out
#SBATCH --error=slurm_logs/bottleneck_stats_%A_%a.err
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=8GB
#SBATCH --array=1-8

OUTPUT_DIR=$PWD
ROOT_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU"
BOTTLENECK_SCRIPT_PATH="$ROOT_DIR/runs/scripts/bottleneck_data.py"
BOTTLENECK_OUTPUT_PATH="$OUTPUT_DIR/bottleneck_data.csv"
CPU_WIDTH=$SLURM_ARRAY_TASK_ID

module load SciPy-bundle/2024.05-gfbf-2024a
module load matplotlib/3.9.2-gfbf-2024a
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/
rm $BOTTLENECK_OUTPUT_PATH

echo "Running bottleneck script for CPU width $CPU_WIDTH..."
python3 $BOTTLENECK_SCRIPT_PATH --base-dir $OUTPUT_DIR/width$CPU_WIDTH \
    --output-dir "$BOTTLENECK_OUTPUT_PATH"
