#!/bin/bash

# Define the base directories
SLURM_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/slurm"
OUTPUT_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/runs/output/wakeupstats/broadcast_proposal_thresholds_v2/"
export OUTPUT_DIR

export MAX_BROADCASTS=1
export MAX_POINTERS=0

# Create a unique output directory for each combination
EXP_OUTPUT_DIR="${OUTPUT_DIR}/${MAX_BROADCASTS}B_${MAX_POINTERS}P"
echo "Submitting jobs for MAX_BROADCASTS=${MAX_BROADCASTS} and MAX_POINTERS=${MAX_POINTERS}"

# Step 1: Submit the code modification job
echo "Submitting code modification job with a dependency on ${RUN_JOB_ID}"
MODIFY_CODE_JOB_ID=$(sbatch --parsable -d "afterok:23102576" -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/modify_code_file.slurm" "${MAX_BROADCASTS}" "${MAX_POINTERS}")

# Step 2: Submit the build job with a dependency on the modify job
echo "Submitting build job with dependency on ${MODIFY_CODE_JOB_ID}..."
BUILD_JOB_ID=$(sbatch --parsable -d "afterok:${MODIFY_CODE_JOB_ID}" -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/build_gem5.slurm")

# Step 3: Submit the simulation job with a dependency on the build job
echo "Submitting run job with dependency on ${BUILD_JOB_ID}..."
RUN_JOB_ID=$(sbatch --parsable -d "afterok:${BUILD_JOB_ID}" -D "${EXP_OUTPUT_DIR}" --array=0-19 "${SLURM_DIR}/multi_width_benchmark_jobs.slurm")

echo "Jobs submitted for this configuration. Final Run Job ID: ${RUN_JOB_ID}"
