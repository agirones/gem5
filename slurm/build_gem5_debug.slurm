#!/bin/bash
#SBATCH --job-name=build_gem5
#SBATCH --chdir=runs/output/build_gem5_debug
#SBATCH --output=slurm_logs/build_gem5_debug.out
#SBATCH --error=slurm_logs/build_gem5_debug.err
#SBATCH --time=00:25:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=12GB

CONTAINER_PATH="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/mast_gem5.sif"
GEM5_DIR=$1

if [ -z "$GEM5_DIR" ]; then
    echo "Warning: No gem5 directory provided, using default"
    GEM5_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/"
fi

cd "${GEM5_DIR}"
apptainer exec -B /cluster:/cluster "${CONTAINER_PATH}" scons -j $(nproc) build/X86/gem5.debug --ignore-style