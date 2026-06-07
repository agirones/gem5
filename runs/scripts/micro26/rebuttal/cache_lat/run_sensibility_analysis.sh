#!/bin/bash
# Sensitivity analysis for micro26/rebuttal/cache_lat: sweep broadcastMax (1–3)
# and dependentsThreshold (−1 to 2) at L1 latency 4, submitting one SLURM job
# per (benchmark, simpoint, configuration) triple.
#
# Output tree:
#   runs/output/micro26/rebuttal/cache_lat/sensibility_analysis/
#     bmax{N}_dt{M}/
#       width8/{benchmark}/{simpoint}/m5out/stats.txt
#       slurm_logs/b{B}_s{S}.{out,err}
#
# Usage:
#   ./run_sensibility_analysis.sh [GEM5_ROOT]

set -euo pipefail

GEM5_ROOT="${1:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
CPT_BASE="${GEM5_CPTS:-/cluster/projects/mast/checkpoints/simpoint-checkpoints}"
NUM_BENCHMARKS=20
CPU_WIDTH=8
L1_LATENCY=4

SENS_BASE="${GEM5_ROOT}/runs/output/micro26/rebuttal/cache_lat/sensibility_analysis"
SLURM_SCRIPT="${GEM5_ROOT}/slurm/single_simpoint_job.slurm"

echo "=== Cache-lat sensibility analysis (L1 latency = ${L1_LATENCY}) ==="
echo "  broadcastMax        : 1 .. 3"
echo "  dependentsThreshold : -1 .. 2"
echo "  CPT_BASE            : ${CPT_BASE}"
echo ""

total_jobs=0

for BROADCAST_MAX in $(seq 1 3); do
    for DEPENDENTS_THRESHOLD in $(seq -1 2); do

        OUTPUT_DIR="${SENS_BASE}/bmax${BROADCAST_MAX}_dt${DEPENDENTS_THRESHOLD}"
        mkdir -p "${OUTPUT_DIR}/slurm_logs"

        echo "--- bmax=${BROADCAST_MAX}  dt=${DEPENDENTS_THRESHOLD}  l1=${L1_LATENCY}  -> ${OUTPUT_DIR}"

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
