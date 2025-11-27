#!/bin/bash

# Define the base directories
BASE_DIR="/cluster/home/andreug/research/EECS-NTNU/"
SLURM_DIR="${BASE_DIR}tmp/slurm/"
OUTPUT_DIR="runs/output/wakeupstats/japanese_fast_no_dest_no_wake_up/"
export OUTPUT_DIR

for MAX_BROADCASTS in $(seq 12 -1 5); do

    GEM5_COPY_DIR="${BASE_DIR}${MAX_BROADCASTS}B/"

    echo "Submitting jobs for MAX_BROADCASTS=${MAX_BROADCASTS}"

    mkdir "${GEM5_COPY_DIR}"
    # Step 1: Submit the gem5 copy job
    echo "Submitting copy gem5 job..."
#    COPY_GEM5_JOB_ID=$(sbatch --job-name copy_gem5 --parsable --output /dev/null \
#        --wrap "cp -r ${BASE_DIR}tmp/README.md ${BASE_DIR}tmp/RELEASE-NOTES.md ${BASE_DIR}tmp/LICENSE ${BASE_DIR}tmp/COPYING ${BASE_DIR}tmp/ext ${BASE_DIR}tmp/site_scons ${BASE_DIR}tmp/build* ${BASE_DIR}tmp/src ${BASE_DIR}tmp/configs ${BASE_DIR}tmp/util ${BASE_DIR}tmp/include ${BASE_DIR}tmp/SConstruct ${GEM5_COPY_DIR}")
    COPY_GEM5_JOB_ID=$(sbatch --job-name copy_gem5 --parsable --output /dev/null \
        --wrap "cp -r ${BASE_DIR}tmp/ ${GEM5_COPY_DIR} && rm ${GEM5_COPY_DIR}runs")

    for MAX_POINTERS in $(seq -1 2); do

        echo "Submitting jobs for MAX_BROADCASTS=${MAX_BROADCASTS} and MAX_POINTERS=${MAX_POINTERS}"
        EXP_OUTPUT_DIR="${GEM5_COPY_DIR}${OUTPUT_DIR}${MAX_BROADCASTS}B_${MAX_POINTERS}P"

        # Step 2: Submit the code modification job
        if [ "$MAX_POINTERS" -eq -1 ]; then
            echo "Submitting modify code job with dependency on ${COPY_GEM5_JOB_ID}..."
#            MODIFY_CODE_JOB_ID=$(sbatch --parsable -D "${EXP_OUTPUT_DIR}" \
            MODIFY_CODE_JOB_ID=$(sbatch --parsable -d "afterok:${COPY_GEM5_JOB_ID}" -D "${EXP_OUTPUT_DIR}" \
                "${SLURM_DIR}modify_broadcast_and_pointers.slurm" "${MAX_BROADCASTS}" "${MAX_POINTERS}" \
                "${GEM5_COPY_DIR}")
        else
            echo "Submitting modify code job with dependency on ${COPY_BACK_JOB_ID}..."
            MODIFY_CODE_JOB_ID=$(sbatch --parsable -d "afterok:${COPY_BACK_JOB_ID}" -D "${EXP_OUTPUT_DIR}" \
                "${SLURM_DIR}modify_broadcast_and_pointers.slurm" "${MAX_BROADCASTS}" "${MAX_POINTERS}" \
                "${GEM5_COPY_DIR}")
        fi

        # Step 3: Submit the build job with a dependency on the modify job
        echo "Submitting build job with dependency on ${MODIFY_CODE_JOB_ID}..."
        BUILD_JOB_ID=$(sbatch --parsable -d "afterok:${MODIFY_CODE_JOB_ID}" -D "${EXP_OUTPUT_DIR}" "${SLURM_DIR}build_gem5.slurm" "${GEM5_COPY_DIR}")

        # Step 4: Submit the simulation job with a dependency on the build job
        echo "Submitting run job with dependency on ${BUILD_JOB_ID}..."
        RUN_JOB_ID=$(sbatch --parsable -d "afterok:${BUILD_JOB_ID}" -D "${EXP_OUTPUT_DIR}" --array=0-19 "${SLURM_DIR}multi_width_benchmark_jobs.slurm")

        # Step 5: Submit the clean up job with a dependency on the run job
        echo "Submitting run clean up with dependency on ${RUN_JOB_ID}..."
        COPY_BACK_JOB_ID=$(sbatch --job-name copy_back --parsable --output /dev/null -d "afterany:${RUN_JOB_ID}" \
            --wrap "cp -r ${EXP_OUTPUT_DIR}/ ${BASE_DIR}gem5-NTNU/${OUTPUT_DIR}${MAX_BROADCASTS}B_${MAX_POINTERS}P")

    done

    sbatch --job-name clean_up --output /dev/null -d "afterok:${COPY_BACK_JOB_ID}" --wrap "rm -r ${GEM5_COPY_DIR}"
    echo "Jobs submitted for this configuration. Final Run Job ID: ${RUN_JOB_ID}"
done
