#!/bin/bash

# Define the base directories
SLURM_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/slurm"
OUTPUT_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/runs/output/wakeupstats/baseline_fast_cache_no_dest_no_wake_up/"
export OUTPUT_DIR

export MAX_BROADCASTS=1

for MAX_BROADCASTS in {8..1}; do
    # Create a unique output directory for each combination
    EXP_OUTPUT_DIR="${OUTPUT_DIR}/${MAX_BROADCASTS}B"
    echo "Submitting jobs for MAX_BROADCASTS=${MAX_BROADCASTS}"

    # Step 1: Submit the code modification job
    if [ "$MAX_BROADCASTS" -eq 8 ]; then
        echo "Submitting code modification job..."
        MODIFY_CODE_JOB_ID=$(sbatch --parsable -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/modify_broadcast_and_pointers.slurm" "${MAX_BROADCASTS}" "0")
    else
        echo "Submitting code modification job with a dependency on ${RUN_JOB_ID}"
        MODIFY_CODE_JOB_ID=$(sbatch --parsable -d "afterany:${RUN_JOB_ID}" -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/modify_broadcast_and_pointers.slurm" "${MAX_BROADCASTS}" "0")
    fi

    # Step 2: Submit the build job with a dependency on the modify job
    echo "Submitting build job with dependency on ${MODIFY_CODE_JOB_ID}..."
    BUILD_JOB_ID=$(sbatch --parsable -d "afterok:${MODIFY_CODE_JOB_ID}" -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/build_gem5.slurm")

    # Step 3: Submit the simulation job with a dependency on the build job
    echo "Submitting run job with dependency on ${BUILD_JOB_ID}..."
    RUN_JOB_ID=$(sbatch --parsable -d "afterok:${BUILD_JOB_ID}" -D "${EXP_OUTPUT_DIR}" --array=0-19 "${SLURM_DIR}/multi_width_benchmark_jobs.slurm")

    echo "Jobs submitted for this configuration. Final Run Job ID: ${RUN_JOB_ID}"
done
