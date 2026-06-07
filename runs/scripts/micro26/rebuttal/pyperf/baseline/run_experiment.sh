#!/bin/bash
# Run pyperformance ffrun jobs for the baseline configuration:
#   broadcastMax=12, dependentsThreshold=-1
#
# Benchmarks (pyperf indices): float (40), nbody (54), chaos (26), go (45),
# richards (74).
#
# Workflow per benchmark:
#   1. single_ffcpt_job.slurm  — post-boot checkpoint (skipped if already present)
#   2. single_ffrun_job.slurm  — atomic FF -> O3 warmup -> measured region
#
# Post-boot checkpoints are shared across configurations and live in
# GEM5_POSTBOOT_CPTS (default: runs/legacy-checkpoints/<bench>-cpt).
#
# Output tree:
#   runs/output/micro26/rebuttal/pyperf/baseline/
#     width8/<bench>/m5out/stats.txt
#     slurm_logs/{ffcpt,ffrun}_<bench>.{out,err}
#
# Usage:
#   ./run_experiment.sh [GEM5_ROOT]

set -euo pipefail

GEM5_ROOT="${1:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
export GEM5_BENCH_SET=pyperf
export GEM5_DISK="${GEM5_DISK:-${GEM5_ROOT}/runs/disk-images/x86-ubuntu-python}"
export GEM5_POSTBOOT_CPTS="${GEM5_POSTBOOT_CPTS:-${GEM5_ROOT}/runs/legacy-checkpoints}"

CPU_WIDTH=8
BROADCAST_MAX=12
DEPENDENTS_THRESHOLD=-1
FAST_FORWARD_LENGTH="${FAST_FORWARD_LENGTH:-2000000000}"
WARMUP_LENGTH="${WARMUP_LENGTH:-50000000}"
MEASURE_LENGTH="${MEASURE_LENGTH:-100000000}"

# float, nbody, chaos, go, richards
BENCHMARK_INDICES=(40 54 26 45 74)

OUTPUT_DIR="${GEM5_ROOT}/runs/output/micro26/rebuttal/pyperf/baseline"
FFCPT_SCRIPT="${GEM5_ROOT}/slurm/single_ffcpt_job.slurm"
FFRUN_SCRIPT="${GEM5_ROOT}/slurm/single_ffrun_job.slurm"

mkdir -p "${OUTPUT_DIR}/slurm_logs" "${GEM5_POSTBOOT_CPTS}"

echo "=== Submitting baseline pyperformance ffrun jobs ==="
echo "  broadcastMax        : ${BROADCAST_MAX}"
echo "  dependentsThreshold : ${DEPENDENTS_THRESHOLD}"
echo "  ff / warmup / meas  : ${FAST_FORWARD_LENGTH} / ${WARMUP_LENGTH} / ${MEASURE_LENGTH}"
echo "  disk                : ${GEM5_DISK}"
echo "  post-boot cpts      : ${GEM5_POSTBOOT_CPTS}"
echo "  output              : ${OUTPUT_DIR}"
echo "  benchmarks          : ${BENCHMARK_INDICES[*]}"
echo ""

total_ffrun=0
total_ffcpt=0

for BENCHMARK_NUM in "${BENCHMARK_INDICES[@]}"; do
    BENCH_NAME=$(GEM5_BENCH_SET=pyperf python3 -c "
import sys
sys.path.insert(0, '${GEM5_ROOT}/configs/mast')
from benchmarks import ALL_BENCHMARKS
print(ALL_BENCHMARKS[${BENCHMARK_NUM}].name)
")

    dep=""
    if [ ! -d "${GEM5_POSTBOOT_CPTS}/${BENCH_NAME}-cpt" ]; then
        echo "[${BENCHMARK_NUM} ${BENCH_NAME}] no post-boot checkpoint -> submitting ffcpt"
        cpt_jid=$(sbatch --parsable \
            --export=ALL,\
BENCHMARK_NUM=${BENCHMARK_NUM},\
CPU_WIDTH=${CPU_WIDTH},\
OUTPUT_DIR=${OUTPUT_DIR},\
GEM5_ROOT=${GEM5_ROOT},\
GEM5_BENCH_SET=pyperf,\
GEM5_DISK=${GEM5_DISK},\
GEM5_POSTBOOT_CPTS=${GEM5_POSTBOOT_CPTS} \
            --output="${OUTPUT_DIR}/slurm_logs/ffcpt_${BENCH_NAME}.out" \
            --error="${OUTPUT_DIR}/slurm_logs/ffcpt_${BENCH_NAME}.err" \
            "${FFCPT_SCRIPT}")
        echo "    ffcpt job: ${cpt_jid}"
        dep="--dependency=afterok:${cpt_jid}"
        total_ffcpt=$((total_ffcpt + 1))
    else
        echo "[${BENCHMARK_NUM} ${BENCH_NAME}] post-boot checkpoint exists -> ffrun only"
    fi

    run_jid=$(sbatch --parsable ${dep} \
        --export=ALL,\
BENCHMARK_NUM=${BENCHMARK_NUM},\
CPU_WIDTH=${CPU_WIDTH},\
BROADCAST_MAX=${BROADCAST_MAX},\
DEPENDENTS_THRESHOLD=${DEPENDENTS_THRESHOLD},\
FAST_FORWARD_LENGTH=${FAST_FORWARD_LENGTH},\
WARMUP_LENGTH=${WARMUP_LENGTH},\
MEASURE_LENGTH=${MEASURE_LENGTH},\
OUTPUT_DIR=${OUTPUT_DIR},\
GEM5_ROOT=${GEM5_ROOT},\
GEM5_BENCH_SET=pyperf,\
GEM5_DISK=${GEM5_DISK},\
GEM5_POSTBOOT_CPTS=${GEM5_POSTBOOT_CPTS} \
        --output="${OUTPUT_DIR}/slurm_logs/ffrun_${BENCH_NAME}.out" \
        --error="${OUTPUT_DIR}/slurm_logs/ffrun_${BENCH_NAME}.err" \
        "${FFRUN_SCRIPT}")
    echo "    ffrun job: ${run_jid}"
    total_ffrun=$((total_ffrun + 1))
done

echo ""
echo "Submitted ${total_ffcpt} ffcpt + ${total_ffrun} ffrun jobs."
echo "Stats: ${OUTPUT_DIR}/width${CPU_WIDTH}/<bench>/m5out/stats.txt"
