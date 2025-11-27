#!/bin/bash

# Define the base directories
SLURM_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/slurm"
OUTPUT_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/runs/output/wakeupstats/baseline_fast_cache/"
export OUTPUT_DIR

for WB_WIDTH in {1..4}; do
    # Create a unique output directory for each combination
    EXP_OUTPUT_DIR="${OUTPUT_DIR}/wb_width${WB_WIDTH}"
    echo "Submitting jobs for WB_WIDTH=${WB_WIDTH}"

    # Step 1: Submit the code modification job
    if [ "$WB_WIDTH" -eq 1 ]; then
        echo "Submitting code modification job..."
        MODIFY_CODE_JOB_ID=$(sbatch --parsable -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/modify_wb_width.slurm" "${WB_WIDTH}")
    else
        echo "Submitting code modification job with a dependency on ${RUN_JOB_ID}"
        MODIFY_CODE_JOB_ID=$(sbatch --parsable -d "afterok:${RUN_JOB_ID}" -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/modify_wb_width.slurm" "${WB_WIDTH}")
    fi

    # Step 2: Submit the simulation job with a dependency on the modify code job
    echo "Submitting run job with dependency on ${MODIFY_CODE_JOB_ID}..."
    RUN_JOB_ID=$(sbatch --parsable -d "afterok:${MODIFY_CODE_JOB_ID}" -D "${EXP_OUTPUT_DIR}" --array=0-19 "${SLURM_DIR}/multi_width_benchmark_jobs.slurm")

    echo "Jobs submitted for this configuration. Final Run Job ID: ${RUN_JOB_ID}"
done
