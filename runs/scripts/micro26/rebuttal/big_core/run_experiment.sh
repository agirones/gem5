#!/bin/bash
# Big-core sweep for micro26/rebuttal: scale the detailed (O3) core by a set of
# --core-scale factors for two core implementations, submitting one SLURM job
# per (implementation, core, benchmark, simpoint) tuple.
#
# The core scale factor multiplies the superscalar widths and structure sizes
# in profile-config-legacy.py (fetch/decode/.../commit widths, IQ/LQ/SQ, ROB and
# physical register files). 1.0 = baseline, 1.5 = x1.5, 2.0 = double,
# 4.0 = quadruple.
#
# Implementations:
#   baseline : broadcastMax=12, dependentsThreshold=-1
#   sereno   : broadcastMax=1,  dependentsThreshold=2
#
# Output tree:
#   runs/output/micro26/rebuttal/big_core/
#     {baseline,sereno}/
#       {1.0x,1.5x,2.0x,4.0x}/
#         width8/{benchmark}/{simpoint}/m5out/stats.txt
#         slurm_logs/b{B}_s{S}.{out,err}
#
# Usage:
#   ./run_experiment.sh [GEM5_ROOT]

set -euo pipefail

GEM5_ROOT="${1:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
CPT_BASE="${GEM5_CPTS:-/cluster/projects/mast/checkpoints/simpoint-checkpoints}"
NUM_BENCHMARKS=20
CPU_WIDTH=8

BIG_CORE_BASE="${GEM5_ROOT}/runs/output/micro26/rebuttal/big_core"
SLURM_SCRIPT="${GEM5_ROOT}/slurm/single_simpoint_job.slurm"

# Core implementations to sweep: name -> "broadcastMax dependentsThreshold"
declare -A IMPL_PARAMS=(
    [baseline]="12 -1"
    [sereno]="1 2"
)

# Core sizes to sweep: directory name -> core scale factor
declare -A CORE_PARAMS=(
    [1.0x]="1.0"
    [1.5x]="1.5"
    [2.0x]="2.0"
    [4.0x]="4.0"
)

# Sweep order (associative arrays are unordered in bash)
IMPL_ORDER=(sereno)
CORE_ORDER=(1.0x 1.5x 2.0x 4.0x)

echo "=== Big-core sweep ==="
echo "  implementations : ${IMPL_ORDER[*]}"
echo "  core sizes      : ${CORE_ORDER[*]}"
echo "  CPT_BASE        : ${CPT_BASE}"
echo ""

total_jobs=0

for IMPL in "${IMPL_ORDER[@]}"; do
    read -r BROADCAST_MAX DEPENDENTS_THRESHOLD <<< "${IMPL_PARAMS[$IMPL]}"

    for CORE in "${CORE_ORDER[@]}"; do
        CORE_SCALE="${CORE_PARAMS[$CORE]}"

        OUTPUT_DIR="${BIG_CORE_BASE}/${IMPL}/${CORE}"
        mkdir -p "${OUTPUT_DIR}/slurm_logs"

        echo "--- impl=${IMPL}  core=${CORE}  (core_scale=${CORE_SCALE}, bmax=${BROADCAST_MAX}, dt=${DEPENDENTS_THRESHOLD})  -> ${OUTPUT_DIR}"

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
CORE_SCALE=${CORE_SCALE},\
BROADCAST_MAX=${BROADCAST_MAX},\
DEPENDENTS_THRESHOLD=${DEPENDENTS_THRESHOLD},\
OUTPUT_DIR=${OUTPUT_DIR},\
GEM5_ROOT=${GEM5_ROOT} \
                    --output="${OUTPUT_DIR}/slurm_logs/b${BENCHMARK_NUM}_s${SIMPOINT_NUM}.out" \
                    --error="${OUTPUT_DIR}/slurm_logs/b${BENCHMARK_NUM}_s${SIMPOINT_NUM}.err" \
                    "${SLURM_SCRIPT}"

                total_jobs=$((total_jobs + 1))
            done

        done
    done
done

echo ""
echo "Submitted ${total_jobs} jobs total."
