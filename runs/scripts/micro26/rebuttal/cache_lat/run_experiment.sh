#!/bin/bash
# Cache latency sweep for micro26/rebuttal: sweep the L1I/L1D tag+data
# latency (2, 3, 4) for two core implementations, submitting one SLURM job
# per (implementation, latency, benchmark, simpoint) tuple.
#
# Implementations:
#   baseline : broadcastMax=12, dependentsThreshold=-1
#   sereno   : broadcastMax=1,  dependentsThreshold=2
#
# Output tree:
#   runs/output/micro26/rebuttal/cache_lat/
#     {baseline,sereno}/
#       {2,3,4}/
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

SENS_BASE="${GEM5_ROOT}/runs/output/micro26/rebuttal/cache_lat"
SLURM_SCRIPT="${GEM5_ROOT}/slurm/single_simpoint_job.slurm"

# Core implementations to sweep: name -> "broadcastMax dependentsThreshold"
declare -A IMPL_PARAMS=(
    [baseline]="12 -1"
    [sereno]="1 2"
)

echo "=== Cache latency sweep ==="
echo "  implementations : baseline sereno"
echo "  L1 latency      : 2 3 4"
echo "  CPT_BASE        : ${CPT_BASE}"
echo ""

total_jobs=0

for IMPL in baseline sereno; do
    read -r BROADCAST_MAX DEPENDENTS_THRESHOLD <<< "${IMPL_PARAMS[$IMPL]}"

    for L1_LATENCY in 2 3 4; do

        OUTPUT_DIR="${SENS_BASE}/${IMPL}/${L1_LATENCY}"
        mkdir -p "${OUTPUT_DIR}/slurm_logs"

        echo "--- impl=${IMPL}  l1_latency=${L1_LATENCY}  (bmax=${BROADCAST_MAX}, dt=${DEPENDENTS_THRESHOLD})  -> ${OUTPUT_DIR}"

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
L1_LATENCY=${L1_LATENCY},\
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
