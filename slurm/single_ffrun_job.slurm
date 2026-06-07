#!/bin/bash
# Run a single gem5 "ffrun" (fast-forward) job as an independent SLURM job.
# This restores the post-boot checkpoint, fast-forwards FAST_FORWARD_LENGTH
# instructions in an atomic CPU, switches to the detailed O3 CPU, warms up
# WARMUP_LENGTH instructions, then measures MEASURE_LENGTH instructions.
#
# All parameters are passed via --export in the sbatch invocation.
#
# Required environment variables:
#   BENCHMARK_NUM   - index into ALL_BENCHMARKS
#   CPU_WIDTH       - processor width (decode/rename/.../commit)
#   OUTPUT_DIR      - base directory for simulation output
#   GEM5_ROOT       - path to the gem5 repository root
#
# Important environment variables for the Python-benchmark workflow:
#   GEM5_DISK            - disk image with Python + deps + the benchmark
#                          (default: the python image under runs/disk-images)
#   GEM5_POSTBOOT_CPTS   - directory holding <bench>-cpt post-boot checkpoints
#                          (default: ${GEM5_ROOT}/runs/legacy-checkpoints)
#
# Optional environment variables (defaults shown):
#   CORE_SCALE            - core scale factor (default 1.0)
#   IQ_SIZE / LQ_SIZE / SQ_SIZE  - (default 256)
#   BROADCAST_MAX         - (default 12)
#   DEPENDENTS_THRESHOLD  - (default -1)
#   L1_LATENCY            - (default 1)
#   FAST_FORWARD_LENGTH   - atomic skip length (default 2000000000 = 2B)
#   WARMUP_LENGTH         - detailed O3 warmup insts (default 50000000 = 50M)
#   MEASURE_LENGTH        - detailed O3 measured insts (default 100000000 = 100M)
#   GEM5_CONFIG           - path to gem5 Python config (default: profile-config-legacy.py)
#
# NOTE on FAST_FORWARD_LENGTH for pyperformance:
#   pyperformance benchmarks are short (a single benchmark typically executes a
#   few billion instructions total, and only a few hundred million for the
#   interpreter startup). A 100B skip would (a) overshoot and exit before the
#   measured region and (b) take many hours even in atomic. The default below
#   (2B) is meant to clear Python startup and land in benchmark steady state.
#   For long-running (e.g. SPEC) workloads via ffrun, override with a larger
#   value. If a run reports "Benchmark exited during fast-forward", reduce it.

#SBATCH --job-name=gem5_ffrun
#SBATCH --output=slurm_logs/ffrun_%A_%a.out
#SBATCH --error=slurm_logs/ffrun_%A_%a.err
#SBATCH --time=0-30:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=25GB

export LMOD_DISABLE_SAME_NAME_AUTOSWAP=no
module load Python/3.12.3-GCCcore-13.3.0

GEM5_ROOT="${GEM5_ROOT:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
GEM5_CONFIG="${GEM5_CONFIG:-${GEM5_ROOT}/configs/mast/profile-config-legacy.py}"

# Python-benchmark disk image and post-boot checkpoint location.
export GEM5_DISK="${GEM5_DISK:-${GEM5_ROOT}/runs/disk-images/x86-ubuntu-python}"
export GEM5_POSTBOOT_CPTS="${GEM5_POSTBOOT_CPTS:-${GEM5_ROOT}/runs/legacy-checkpoints}"

CORE_SCALE="${CORE_SCALE:-1.0}"
IQ_SIZE="${IQ_SIZE:-256}"
LQ_SIZE="${LQ_SIZE:-256}"
SQ_SIZE="${SQ_SIZE:-256}"
BROADCAST_MAX="${BROADCAST_MAX:-12}"
DEPENDENTS_THRESHOLD="${DEPENDENTS_THRESHOLD:--1}"
L1_LATENCY="${L1_LATENCY:-1}"
FAST_FORWARD_LENGTH="${FAST_FORWARD_LENGTH:-2000000000}"
WARMUP_LENGTH="${WARMUP_LENGTH:-50000000}"
MEASURE_LENGTH="${MEASURE_LENGTH:-100000000}"
export GEM5_BENCH_SET="${GEM5_BENCH_SET:-pyperf}"

echo "=== gem5 single ffrun job ==="
echo "  Job ID    : ${SLURM_JOB_ID}"
echo "  Benchmark : ${BENCHMARK_NUM}"
echo "  CPU width : ${CPU_WIDTH}"
echo "  Core scale: ${CORE_SCALE}"
echo "  IQ/LQ/SQ  : ${IQ_SIZE}/${LQ_SIZE}/${SQ_SIZE}"
echo "  bcastMax  : ${BROADCAST_MAX}  dep-thresh: ${DEPENDENTS_THRESHOLD}"
echo "  L1 latency: ${L1_LATENCY}"
echo "  fast-fwd  : ${FAST_FORWARD_LENGTH}"
echo "  warmup    : ${WARMUP_LENGTH}  measure: ${MEASURE_LENGTH}"
echo "  disk      : ${GEM5_DISK}"
echo "  cpt dir   : ${GEM5_POSTBOOT_CPTS}"
echo "  Output dir: ${OUTPUT_DIR}"
echo "================================"

mkdir -p "${OUTPUT_DIR}/slurm_logs"

cd "${GEM5_ROOT}"

python3 "${GEM5_ROOT}/configs/mast/invoke-run.py" \
    --benchmark-num  "${BENCHMARK_NUM}"  \
    --mode           ffrun               \
    --cpu-width      "${CPU_WIDTH}"      \
    --core-scale     "${CORE_SCALE}"     \
    --output-dir     "${OUTPUT_DIR}"     \
    --config         "${GEM5_CONFIG}"    \
    --iq-size        "${IQ_SIZE}"        \
    --lq-size              "${LQ_SIZE}"              \
    --sq-size              "${SQ_SIZE}"              \
    --broadcastMax         "${BROADCAST_MAX}"        \
    --dependentsThreshold  "${DEPENDENTS_THRESHOLD}" \
    --l1-latency           "${L1_LATENCY}"           \
    --warmup-length        "${WARMUP_LENGTH}"        \
    --fast-forward-length  "${FAST_FORWARD_LENGTH}"  \
    --measure-length       "${MEASURE_LENGTH}"
