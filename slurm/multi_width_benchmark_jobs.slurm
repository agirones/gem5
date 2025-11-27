#!/bin/bash

#SBATCH --job-name=benchmark_jobs_multi_width
#SBATCH --output=slurm_logs/benchmark_%A_%a.out
#SBATCH --error=slurm_logs/benchmark_%A_%a.err
#SBATCH --array=0-159
#SBATCH --time=7-00:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=128GB

OUTPUT_DIR="$PWD"
export OUTPUT_DIR
NUM_BENCHMARKS=20
NUM_CPU_WIDTHS=8

GEM5_ROOT=$1
if [ -z "$GEM5_ROOT" ]; then
    echo "Warning: No gem5 base directory provided, using default"
    GEM5_ROOT="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU"
fi

SCRIPT_PATH="${GEM5_ROOT}/configs/mast/invoke-run.py"
GEM5_CONFIG="${GEM5_ROOT}/configs/mast/profile-config-legacy.py"

# Calculate the benchmark number and cpu width from the array ID
BENCHMARK_NUM=$((SLURM_ARRAY_TASK_ID % NUM_BENCHMARKS))
CPU_WIDTH=$((8 - (SLURM_ARRAY_TASK_ID / NUM_BENCHMARKS)))

module load Python/3.12.3-GCCcore-13.3.0

cd "${GEM5_ROOT}"

cp "${GEM5_CONFIG}" "${OUTPUT_DIR}/gem5_config.py"

echo "Running simulation for benchmark $BENCHMARK_NUM with CPU width $CPU_WIDTH..."
python3 "${SCRIPT_PATH}" --benchmark-num "${BENCHMARK_NUM}" --mode simrun --cpu-width "${CPU_WIDTH}" \
                         --output-dir "${OUTPUT_DIR}" --config "${GEM5_CONFIG}"
#python3 "${SCRIPT_PATH}" --benchmark-num "${BENCHMARK_NUM}" --mode cpt --cpt 8 --cpu-width "${CPU_WIDTH}" \

#if [ $SLURM_ARRAY_TASK_ID -eq 0 ]; then
#    echo "All benchmark jobs for this array: $SLURM_ARRAY_JOB_ID"
    
#    echo "Submitting plot_stats array job for CPU widths 1 to $NUM_CPU_WIDTHS, dependent on main job array $SLURM_ARRAY_JOB_ID"
#    sbatch --dependency=afterok:$SLURM_ARRAY_JOB_ID \
#           --chdir="${OUTPUT_DIR}" \
#           --array=1-$NUM_CPU_WIDTHS \
#           --export=OUTPUT_DIR \
#           "${GEM5_ROOT}/slurm/plot_stats.slurm"

#    echo "Submitting bottleneck job dependent on main job array $SLURM_ARRAY_JOB_ID"
#    sbatch --dependency=afterok:$SLURM_ARRAY_JOB_ID \
#           --chdir=$OUTPUT_DIR \
#           --array=1-$NUM_CPU_WIDTHS \
#           "${GEM5_ROOT}/slurm/bottleneck_stats.slurm"
#fi
