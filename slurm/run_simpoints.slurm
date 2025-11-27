#!/bin/bash
#SBATCH --job-name=benchmark_jobs
#SBATCH --output=benchmark_output_%A_%a.txt
#SBATCH --error=benchmark_error_%A_%a.txt
#SBATCH --array=0-19  # Loop over the 20 benchmarks (from index 0 to 19)
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=1  # Number of CPUs per task
#SBATCH --mem=32GB  # Memory allocation per task

# Load the required Python module
module load Python/3.12.3-GCCcore-13.3.0

# Navigate to the directory where the Python script should be called from
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/

# Path to your Python script
SCRIPT_PATH="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/configs/mast/invoke-run.py"

# Run the scons build command
#echo "Running scons build..."
#scons -j $(nproc) build/X86/gem5.opt

# Extract the benchmark index from the SLURM_ARRAY_TASK_ID
BENCHMARK_NUM=${SLURM_ARRAY_TASK_ID}

# Run the Python script with the benchmark index as an argument
echo "Running Python script for benchmark number $BENCHMARK_NUM..."
python3 $SCRIPT_PATH --benchmark-num $BENCHMARK_NUM --mode simrun

