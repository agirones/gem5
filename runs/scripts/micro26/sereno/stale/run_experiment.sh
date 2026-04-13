#!/bin/bash
# Run gem5 simpoint jobs for Sereno stale: broadcastMax=1, dependentsThreshold=2
# with squash-induced broadcast tracking (branch 'sereno-stale').
#
# This version requires a gem5 binary built from the 'sereno-stale' branch.
# Point GEM5_ROOT_V2 at a workspace where that binary has been compiled, or
# set GEM5_BINARY explicitly.
#
# Usage:
#   ./run_experiment.sh [GEM5_ROOT] [GEM5_ROOT_V2]
#
#   GEM5_ROOT     – gem5 repository used for configs, checkpoints, scripts
#                   (default: the standard gem5-NTNU checkout)
#   GEM5_ROOT_V2  – gem5 root containing the sereno-stale binary at
#                   build/X86/gem5.opt
#                   (default: same as GEM5_ROOT; override if you built in a
#                    separate directory or worktree)

set -euo pipefail

GEM5_ROOT="${1:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
# If you built the sereno-stale binary in a separate git worktree, set this:
GEM5_ROOT_V2="${2:-${GEM5_ROOT}}"
CPT_BASE="${GEM5_CPTS:-/cluster/projects/mast/checkpoints/simpoint-checkpoints}"
NUM_BENCHMARKS=20
CPU_WIDTH=8
BROADCAST_MAX=1
DEPENDENTS_THRESHOLD=2

OUTPUT_DIR="${GEM5_ROOT}/runs/output/micro26/sereno/stale"
SLURM_SCRIPT="${GEM5_ROOT}/slurm/single_simpoint_job.slurm"

mkdir -p "${OUTPUT_DIR}/slurm_logs"

echo "=== Submitting Sereno stale jobs (broadcastMax=${BROADCAST_MAX}, dependentsThreshold=${DEPENDENTS_THRESHOLD}, squash-induced broadcast tracking) ==="
echo "    gem5 binary from: ${GEM5_ROOT_V2}/build/X86/gem5.opt"

total_jobs=0

for BENCHMARK_NUM in $(seq 0 $((NUM_BENCHMARKS - 1))); do
    BENCH_NAME=$(python3 -c "
import sys
sys.path.insert(0, '${GEM5_ROOT}/configs/mast')
from benchmarks import ALL_BENCHMARKS
print(ALL_BENCHMARKS[${BENCHMARK_NUM}].name)
")

    CPT_DIR="${CPT_BASE}/${BENCH_NAME}-cpt"

    if [ ! -d "${CPT_DIR}" ]; then
        echo "  [SKIP] benchmark ${BENCHMARK_NUM} (${BENCH_NAME}): checkpoint dir not found"
        continue
    fi

    mapfile -t CPTS < <(ls "${CPT_DIR}" | grep '^cpt\.simpoint_' | sort)
    NUM_SIMPOINTS=${#CPTS[@]}

    if [ "${NUM_SIMPOINTS}" -eq 0 ]; then
        echo "  [SKIP] benchmark ${BENCHMARK_NUM} (${BENCH_NAME}): no checkpoints"
        continue
    fi

    for SIMPOINT_NUM in $(seq 0 $((NUM_SIMPOINTS - 1))); do
        sbatch \
            --export=ALL,\
BENCHMARK_NUM=${BENCHMARK_NUM},\
SIMPOINT_NUM=${SIMPOINT_NUM},\
CPU_WIDTH=${CPU_WIDTH},\
BROADCAST_MAX=${BROADCAST_MAX},\
DEPENDENTS_THRESHOLD=${DEPENDENTS_THRESHOLD},\
OUTPUT_DIR=${OUTPUT_DIR},\
GEM5_ROOT=${GEM5_ROOT_V2} \
            --output="${OUTPUT_DIR}/slurm_logs/b${BENCHMARK_NUM}_s${SIMPOINT_NUM}.out" \
            --error="${OUTPUT_DIR}/slurm_logs/b${BENCHMARK_NUM}_s${SIMPOINT_NUM}.err" \
            "${SLURM_SCRIPT}"
        total_jobs=$((total_jobs + 1))
    done
done

echo "Submitted ${total_jobs} jobs."
