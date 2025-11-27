#!/bin/bash
#SBATCH --job-name=build_gem5
#SBATCH --chdir=runs/output/build_gem5
#SBATCH --output=slurm_logs/build_gem5_%A.out
#SBATCH --error=slurm_logs/build_gem5_%A.err
#SBATCH --time=00:25:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=12GB

module load Python/3.12.3-GCCcore-13.3.0

GEM5_DIR=$1

if [ -z "$GEM5_DIR" ]; then
    echo "Warning: No gem5 directory provided, using default"
    GEM5_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/"
fi

cd "${GEM5_DIR}"
scons -j $(nproc) build/X86/gem5.opt
