#!/bin/bash
# Build gem5 and run the warmup-50M experiment for EDF, Hybrid-WL, and N-Use.
#
# For each implementation this script:
#   1. Checks out the corresponding git branch
#   2. Submits slurm/build_gem5.slurm and waits for completion
#   3. Verifies runs/output/build_gem5/slurm_logs/build_gem5.out ends with
#      "scons: done building targets."
#   4. Submits all simpoint jobs (warmup=50M, L1 latency=1)
#   5. Waits for simpoint jobs to finish before moving to the next branch
#
# Output:
#   runs/output/micro26/rebuttal/warmup/{edf,hybrid-wl,n-use}/50M/
#
# Usage:
#   ./build_and_run_alt_implementations.sh [GEM5_ROOT]
#
# Optional environment variables:
#   SKIP_BUILD=1          Skip the build step (reuse existing binary)
#   SKIP_WAIT_SIMS=1      Submit sims but do not wait before the next branch
#   IMPLEMENTATIONS       Space-separated subset, e.g. "edf hybrid-wl"

set -euo pipefail

GEM5_ROOT="${1:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SLURM="${GEM5_ROOT}/slurm/build_gem5.slurm"
BUILD_LOG="${GEM5_ROOT}/runs/output/build_gem5/slurm_logs/build_gem5.out"
BUILD_SUCCESS_MSG="scons: done building targets."

POLL_INTERVAL="${POLL_INTERVAL:-30}"

declare -A IMPL_BRANCH=(
    [edf]="explicit-data-forwarding"
    [hybrid-wl]="hybrid-wl"
    [n-use]="n-use/InO"
)

declare -A IMPL_RUN_SCRIPT=(
    [edf]="${SCRIPT_DIR}/edf/run_experiment.sh"
    [hybrid-wl]="${SCRIPT_DIR}/hybrid-wl/run_experiment.sh"
    [n-use]="${SCRIPT_DIR}/n-use/run_experiment.sh"
)

if [ -n "${IMPLEMENTATIONS:-}" ]; then
    read -r -a IMPL_LIST <<< "${IMPLEMENTATIONS}"
else
    IMPL_LIST=(edf hybrid-wl n-use)
fi

normalize_job_id() {
    local raw="$1"
    echo "${raw##*;}"
}

wait_for_job() {
    local job_id="$1"
    local label="$2"

    echo "Waiting for ${label} (job ${job_id})..."
    while squeue -j "${job_id}" -h 2>/dev/null | grep -q .; do
        sleep "${POLL_INTERVAL}"
    done

    local state
    state=$(sacct -j "${job_id}" --format=State --noheader -n 2>/dev/null | head -1 | awk '{print $1}')
    if [ "${state}" != "COMPLETED" ]; then
        echo "ERROR: ${label} job ${job_id} finished with state '${state}'"
        exit 1
    fi
    echo "${label} job ${job_id} completed."
}

verify_build_log() {
    if [ ! -f "${BUILD_LOG}" ]; then
        echo "ERROR: build log not found: ${BUILD_LOG}"
        exit 1
    fi

    local last_line
    last_line=$(tail -n 1 "${BUILD_LOG}")
    if [ "${last_line}" != "${BUILD_SUCCESS_MSG}" ]; then
        echo "ERROR: build log does not end with expected success message."
        echo "  expected: ${BUILD_SUCCESS_MSG}"
        echo "  got     : ${last_line}"
        echo ""
        echo "Last 20 lines of ${BUILD_LOG}:"
        tail -n 20 "${BUILD_LOG}"
        exit 1
    fi
    echo "Build verified: ${BUILD_SUCCESS_MSG}"
}

wait_for_job_file() {
    local job_file="$1"
    local label="$2"

    if [ ! -s "${job_file}" ]; then
        echo "WARNING: no ${label} jobs were submitted."
        return 0
    fi

    echo "Waiting for ${label} simulation jobs..."
    while true; do
        local pending=0
        while IFS= read -r job_id; do
            [ -z "${job_id}" ] && continue
            if squeue -j "${job_id}" -h 2>/dev/null | grep -q .; then
                pending=$((pending + 1))
            fi
        done < "${job_file}"

        if [ "${pending}" -eq 0 ]; then
            break
        fi
        echo "  ${pending} ${label} job(s) still running..."
        sleep "${POLL_INTERVAL}"
    done
    echo "All ${label} simulation jobs finished."
}

submit_build() {
    (
        cd "${GEM5_ROOT}"
        sbatch --parsable "${BUILD_SLURM}" "${GEM5_ROOT}"
    )
}

restore_branch() {
    if [ -n "${ORIG_BRANCH:-}" ]; then
        echo "Restoring original branch: ${ORIG_BRANCH}"
        git -C "${GEM5_ROOT}" checkout "${ORIG_BRANCH}"
    fi
}

if ! git -C "${GEM5_ROOT}" diff-index --quiet HEAD --; then
    echo "ERROR: ${GEM5_ROOT} has uncommitted changes."
    echo "Commit or stash them before running this script."
    exit 1
fi

ORIG_BRANCH=$(git -C "${GEM5_ROOT}" rev-parse --abbrev-ref HEAD)
trap restore_branch EXIT

echo "=== Warmup 50M: build + run alternate implementations ==="
echo "  GEM5_ROOT     : ${GEM5_ROOT}"
echo "  start branch  : ${ORIG_BRANCH}"
echo "  implementations: ${IMPL_LIST[*]}"
echo "  SKIP_BUILD    : ${SKIP_BUILD:-0}"
echo "  SKIP_WAIT_SIMS: ${SKIP_WAIT_SIMS:-0}"
echo ""

for impl in "${IMPL_LIST[@]}"; do
    branch="${IMPL_BRANCH[$impl]:-}"
    run_script="${IMPL_RUN_SCRIPT[$impl]:-}"

    if [ -z "${branch}" ] || [ -z "${run_script}" ]; then
        echo "ERROR: unknown implementation '${impl}'"
        exit 1
    fi
    if [ ! -x "${run_script}" ] && [ ! -f "${run_script}" ]; then
        echo "ERROR: run script not found: ${run_script}"
        exit 1
    fi

    echo "============================================================"
    echo "Implementation: ${impl}"
    echo "  branch      : ${branch}"
    echo "  run script  : ${run_script}"
    echo "============================================================"

    echo "Checking out ${branch}..."
    git -C "${GEM5_ROOT}" checkout "${branch}"

    if [ "${SKIP_BUILD:-0}" != "1" ]; then
        echo "Submitting gem5 build..."
        build_job_id=$(submit_build)
        build_job_id=$(normalize_job_id "${build_job_id}")
        wait_for_job "${build_job_id}" "build_gem5 (${impl})"
        verify_build_log
    else
        echo "SKIP_BUILD=1: skipping build step."
        verify_build_log
    fi

    job_ids_file=$(mktemp)
    export JOB_IDS_FILE="${job_ids_file}"
    bash "${run_script}" "${GEM5_ROOT}"
    unset JOB_IDS_FILE

    if [ "${SKIP_WAIT_SIMS:-0}" != "1" ]; then
        wait_for_job_file "${job_ids_file}" "${impl}"
    else
        echo "SKIP_WAIT_SIMS=1: not waiting for ${impl} simulation jobs."
    fi
    rm -f "${job_ids_file}"

    echo ""
done

echo "All requested implementations finished."
echo "Results under: ${GEM5_ROOT}/runs/output/micro26/rebuttal/warmup/{edf,hybrid-wl,n-use}/50M/"
