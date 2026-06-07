#!/bin/bash
# Drive the pyperformance fast-forward (ffrun) workflow on SLURM.
#
# For each requested pyperformance benchmark index it:
#   1. submits a post-boot checkpoint-generation job (single_ffcpt_job.slurm)
#      IF the post-boot checkpoint does not already exist, then
#   2. submits the fast-forward measurement job (single_ffrun_job.slurm),
#      chained with --dependency=afterok on the checkpoint job.
#
# Output tree:
#   runs/output/pyperf/ffrun/
#     width8/<bench>/m5out/stats.txt
#     slurm_logs/...
#   runs/legacy-checkpoints/<bench>-cpt           (post-boot checkpoints)
#
# Usage:
#   ./run_pyperf_ffrun.sh [BENCH_INDICES...]
#   (default indices: a few CPU-bound benchmarks; see DEFAULT_INDICES below)
#
# Tunables via env:
#   FAST_FORWARD_LENGTH (default 2000000000 = 2B)  WARMUP_LENGTH (50M)
#   MEASURE_LENGTH (100M)  CPU_WIDTH (8)

set -euo pipefail

GEM5_ROOT="${GEM5_ROOT:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
export GEM5_BENCH_SET=pyperf
export GEM5_DISK="${GEM5_DISK:-${GEM5_ROOT}/runs/disk-images/x86-ubuntu-python}"
export GEM5_POSTBOOT_CPTS="${GEM5_POSTBOOT_CPTS:-${GEM5_ROOT}/runs/legacy-checkpoints}"

CPU_WIDTH="${CPU_WIDTH:-8}"
FAST_FORWARD_LENGTH="${FAST_FORWARD_LENGTH:-2000000000}"
WARMUP_LENGTH="${WARMUP_LENGTH:-50000000}"
MEASURE_LENGTH="${MEASURE_LENGTH:-100000000}"

OUTPUT_DIR="${OUTPUT_DIR:-${GEM5_ROOT}/runs/output/pyperf/ffrun}"
FFCPT_SCRIPT="${GEM5_ROOT}/slurm/single_ffcpt_job.slurm"
FFRUN_SCRIPT="${GEM5_ROOT}/slurm/single_ffrun_job.slurm"

# float, nbody, chaos, go, richards (CPU-bound, good gem5 fits)
DEFAULT_INDICES=(40 54 26 45 74)
if [ "$#" -gt 0 ]; then
    INDICES=("$@")
else
    INDICES=("${DEFAULT_INDICES[@]}")
fi

mkdir -p "${OUTPUT_DIR}/slurm_logs" "${GEM5_POSTBOOT_CPTS}"

echo "=== pyperformance ffrun submission ==="
echo "  disk      : ${GEM5_DISK}"
echo "  cpt dir   : ${GEM5_POSTBOOT_CPTS}"
echo "  output    : ${OUTPUT_DIR}"
echo "  ff/warm/m : ${FAST_FORWARD_LENGTH}/${WARMUP_LENGTH}/${MEASURE_LENGTH}"
echo "  indices   : ${INDICES[*]}"
echo ""

for BENCHMARK_NUM in "${INDICES[@]}"; do
    NAME=$(python3 -c "
import sys
sys.path.insert(0, '${GEM5_ROOT}/configs/mast')
from benchmarks import ALL_BENCHMARKS
print(ALL_BENCHMARKS[${BENCHMARK_NUM}].name)
")
    dep=""
    if [ ! -d "${GEM5_POSTBOOT_CPTS}/${NAME}-cpt" ]; then
        echo "[${BENCHMARK_NUM} ${NAME}] no post-boot checkpoint -> submitting ffcpt"
        cpt_jid=$(sbatch --parsable \
            --export=ALL,BENCHMARK_NUM=${BENCHMARK_NUM},CPU_WIDTH=${CPU_WIDTH},OUTPUT_DIR=${OUTPUT_DIR},GEM5_ROOT=${GEM5_ROOT},GEM5_BENCH_SET=pyperf,GEM5_DISK=${GEM5_DISK},GEM5_POSTBOOT_CPTS=${GEM5_POSTBOOT_CPTS} \
            --output="${OUTPUT_DIR}/slurm_logs/ffcpt_${NAME}.out" \
            --error="${OUTPUT_DIR}/slurm_logs/ffcpt_${NAME}.err" \
            "${FFCPT_SCRIPT}")
        echo "    ffcpt job: ${cpt_jid}"
        dep="--dependency=afterok:${cpt_jid}"
    else
        echo "[${BENCHMARK_NUM} ${NAME}] post-boot checkpoint exists -> ffrun only"
    fi

    run_jid=$(sbatch --parsable ${dep} \
        --export=ALL,BENCHMARK_NUM=${BENCHMARK_NUM},CPU_WIDTH=${CPU_WIDTH},OUTPUT_DIR=${OUTPUT_DIR},GEM5_ROOT=${GEM5_ROOT},GEM5_BENCH_SET=pyperf,GEM5_DISK=${GEM5_DISK},GEM5_POSTBOOT_CPTS=${GEM5_POSTBOOT_CPTS},FAST_FORWARD_LENGTH=${FAST_FORWARD_LENGTH},WARMUP_LENGTH=${WARMUP_LENGTH},MEASURE_LENGTH=${MEASURE_LENGTH} \
        --output="${OUTPUT_DIR}/slurm_logs/ffrun_${NAME}.out" \
        --error="${OUTPUT_DIR}/slurm_logs/ffrun_${NAME}.err" \
        "${FFRUN_SCRIPT}")
    echo "    ffrun job: ${run_jid}"
done

echo ""
echo "Submitted. Watch with: squeue -u \$USER"
echo "Stats land in: ${OUTPUT_DIR}/width${CPU_WIDTH}/<bench>/m5out/stats.txt"
