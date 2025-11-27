#!/bin/bash

# Define the base directories
SLURM_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/slurm"
OUTPUT_DIR="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/runs/output/wakeupstats/broadcast_proposal_thresholds_debug/"
export OUTPUT_DIR

for MAX_BROADCASTS in {1..3}; do
    for MAX_POINTERS in {1..3}; do
        # Create a unique output directory for each combination
        EXP_OUTPUT_DIR="${OUTPUT_DIR}/${MAX_BROADCASTS}B_${MAX_POINTERS}P"
        echo "Submitting jobs for MAX_BROADCASTS=${MAX_BROADCASTS} and MAX_POINTERS=${MAX_POINTERS}"

        # Step 1: Submit the code modification job
        if [ "$MAX_BROADCASTS" -eq 1 ] && [ "$MAX_POINTERS" -eq 1 ]; then
            echo "Submitting code modification job..."
            MODIFY_CODE_JOB_ID=$(sbatch --parsable -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/modify_code_file.slurm" "${MAX_BROADCASTS}" "${MAX_POINTERS}")
        else
            echo "Submitting code modification job with a dependency on ${RUN_JOB_ID}"
            MODIFY_CODE_JOB_ID=$(sbatch --parsable -d "afterok:${RUN_JOB_ID}" -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/modify_code_file.slurm" "${MAX_BROADCASTS}" "${MAX_POINTERS}")
        fi

        # Step 2: Submit the build job with a dependency on the modify job
        echo "Submitting build job with dependency on ${MODIFY_CODE_JOB_ID}..."
        BUILD_JOB_ID=$(sbatch --parsable -d "afterok:${MODIFY_CODE_JOB_ID}" -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}/build_gem5.slurm")

        # Step 3: Submit the simulation job with a dependency on the build job
        if [ "$MAX_BROADCASTS" -eq 1 ] && [ "$MAX_POINTERS" -eq 1 ]; then
            echo "Submitting run job with dependency on ${BUILD_JOB_ID}..."
            RUN_JOB_ID=$(sbatch --parsable -d "afterok:${BUILD_JOB_ID}" -D "${EXP_OUTPUT_DIR}" --array=11 "${SLURM_DIR}/multi_width_benchmark_jobs.slurm")
        elif [ "$MAX_BROADCASTS" -eq 1 ] && [ "$MAX_POINTERS" -eq 2 ]; then
            echo "Submitting run job with dependency on ${BUILD_JOB_ID}..."
            RUN_JOB_ID=$(sbatch --parsable -d "afterok:${BUILD_JOB_ID}" -D "${EXP_OUTPUT_DIR}" --array=5,11 "${SLURM_DIR}/multi_width_benchmark_jobs.slurm")
        else
            echo "Submitting run job with dependency on ${BUILD_JOB_ID}..."
            RUN_JOB_ID=$(sbatch --parsable -d "afterok:${BUILD_JOB_ID}" -D "${EXP_OUTPUT_DIR}" --array=5 "${SLURM_DIR}/multi_width_benchmark_jobs.slurm")
        fi

        echo "Jobs submitted for this configuration. Final Run Job ID: ${RUN_JOB_ID}"
    done
done
