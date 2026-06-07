#!/bin/bash
# Warmup-sensitivity sweep for micro26/rebuttal: compare a 10M vs 50M detailed
# (O3) warmup for two core implementations, submitting one SLURM job per
# (implementation, warmup, benchmark, simpoint) tuple.
#
# Both warmup variants measure the SAME 50M-instruction window so the results
# are directly comparable.  Given the existing checkpoints were taken 10M
# instructions before the SimPoint (warmup=10M at checkpoint time), the only
# window reachable by both a 10M and a 50M detailed warmup is
# [checkpoint+50M, checkpoint+100M]:
#
#   50M : WARMUP_LENGTH=50M, FAST_FORWARD_LENGTH=0
#         -> O3 restores from the checkpoint and warms up 50M, then measures.
#   10M : WARMUP_LENGTH=10M, FAST_FORWARD_LENGTH=40M
#         -> atomic CPU fast-forwards 40M (caches flushed at the switch), then
#            the O3 CPU warms up 10M cold, then measures.
#
# In both cases WARMUP_LENGTH + FAST_FORWARD_LENGTH = 50M, keeping the measured
# region aligned.
#
# Implementations:
#   baseline : broadcastMax=12, dependentsThreshold=-1
#   sereno   : broadcastMax=1,  dependentsThreshold=2
#
# Output tree:
#   runs/output/micro26/rebuttal/warmup/
#     {baseline,sereno}/
#       {10M,50M}/
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

SENS_BASE="${GEM5_ROOT}/runs/output/micro26/rebuttal/warmup"
SLURM_SCRIPT="${GEM5_ROOT}/slurm/single_simpoint_job.slurm"

# Core implementations to sweep: name -> "broadcastMax dependentsThreshold"
declare -A IMPL_PARAMS=(
    [baseline]="12 -1"
    [sereno]="1 2"
)

# Warmup variants: name -> "WARMUP_LENGTH FAST_FORWARD_LENGTH"
# (warmup + fast-forward must stay constant so the measured window is identical)
declare -A WARMUP_PARAMS=(
    [50M]="50000000 0"
    [10M]="10000000 40000000"
)

echo "=== Warmup sensitivity sweep ==="
echo "  implementations : baseline sereno"
echo "  warmup variants : 10M 50M  (measured window fixed at +50M..+100M)"
echo "  CPT_BASE        : ${CPT_BASE}"
echo ""

total_jobs=0

for IMPL in baseline sereno; do
    read -r BROADCAST_MAX DEPENDENTS_THRESHOLD <<< "${IMPL_PARAMS[$IMPL]}"

    for WARMUP in 50M 10M; do
        read -r WARMUP_LENGTH FAST_FORWARD_LENGTH <<< "${WARMUP_PARAMS[$WARMUP]}"

        OUTPUT_DIR="${SENS_BASE}/${IMPL}/${WARMUP}"
        mkdir -p "${OUTPUT_DIR}/slurm_logs"

        echo "--- impl=${IMPL}  warmup=${WARMUP}  (wu=${WARMUP_LENGTH}, ff=${FAST_FORWARD_LENGTH}, bmax=${BROADCAST_MAX}, dt=${DEPENDENTS_THRESHOLD})  -> ${OUTPUT_DIR}"

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
WARMUP_LENGTH=${WARMUP_LENGTH},\
FAST_FORWARD_LENGTH=${FAST_FORWARD_LENGTH},\
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
