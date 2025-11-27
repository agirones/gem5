#!/bin/bash
#SBATCH --job-name=debug_benchmark_single
#SBATCH --output=debug_output.txt
#SBATCH --error=debug_error.txt
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=32GB

module load Python/3.11.5-GCCcore-13.2.0

cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/

SCRIPT_PATH="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/configs/mast/invoke-run.py"
GEM5_ROOT="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU"
GEM5_CONFIG="${GEM5_ROOT}/configs/mast/profile-config-legacy.py"

# --- Hardcode the values for debugging ---
BENCHMARK_NUM=0   # Change this to the specific benchmark number you want (e.g., 0, 1, 2, etc.)
CPU_WIDTH=8       # Change this to the specific CPU width you want (e.g., 1, 2, 4, 8)
CPT_NUM=0       # Change this to the specific CPU width you want (e.g., 1, 2, 4, 8)
# ----------------------------------------

echo "Running debug simulation for benchmark $BENCHMARK_NUM with CPU width $CPU_WIDTH..."
python3 "${SCRIPT_PATH}" --benchmark-num "${BENCHMARK_NUM}" --mode cpt --cpt "${CPT_NUM}" \
                         --cpu-width "${CPU_WIDTH}" --config "${GEM5_CONFIG}"

# Remove the post-processing sbatch command unless you specifically need it for this single debug run
# if [ $SLURM_ARRAY_TASK_ID -eq 0 ]; then
#sbatch --dependency=afterok:$SLURM_JOB_ID --job-name=post_processing slurm/plot_stats.slurm
# fi
