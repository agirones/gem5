#!/bin/bash
# Run a single gem5 simpoint as an independent SLURM job.
# All parameters are passed via --export in the sbatch invocation.
#
# Required environment variables:
#   BENCHMARK_NUM   - index into ALL_BENCHMARKS
#   SIMPOINT_NUM    - simpoint index within the benchmark
#   CPU_WIDTH       - processor width (decode/rename/.../commit)
#   OUTPUT_DIR      - base directory for simulation output
#   GEM5_ROOT       - path to the gem5 repository root
#
# Optional environment variables (defaults match invoke-run.py defaults):
#   I_BUFFER_HEAD   - (default 1)
#   I_BUFFER_SIZE   - (default 256)
#   IQ_SIZE         - (default 256)
#   LQ_SIZE         - (default 256)
#   SQ_SIZE         - (default 256)
#   N_SLOTS               - (default 2)
#   BROADCAST_MAX         - (default 12)
#   DEPENDENTS_THRESHOLD  - (default -1)
#   GEM5_CONFIG           - path to gem5 Python config (default: profile-config-legacy.py)

#SBATCH --job-name=gem5_simpoint
#SBATCH --output=slurm_logs/simpoint_%A_%a.out
#SBATCH --error=slurm_logs/simpoint_%A_%a.err
#SBATCH --time=0-30:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=25GB

export LMOD_DISABLE_SAME_NAME_AUTOSWAP=no
module load Python/3.12.3-GCCcore-13.3.0

GEM5_ROOT="${GEM5_ROOT:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
GEM5_CONFIG="${GEM5_CONFIG:-${GEM5_ROOT}/configs/mast/profile-config-legacy.py}"

IQ_SIZE="${IQ_SIZE:-256}"
LQ_SIZE="${LQ_SIZE:-256}"
SQ_SIZE="${SQ_SIZE:-256}"
BROADCAST_MAX="${BROADCAST_MAX:-12}"
DEPENDENTS_THRESHOLD="${DEPENDENTS_THRESHOLD:--1}"

echo "=== gem5 single-simpoint job ==="
echo "  Job ID    : ${SLURM_JOB_ID}"
echo "  Benchmark : ${BENCHMARK_NUM}"
echo "  Simpoint  : ${SIMPOINT_NUM}"
echo "  CPU width : ${CPU_WIDTH}"
echo "  IQ/LQ/SQ  : ${IQ_SIZE}/${LQ_SIZE}/${SQ_SIZE}"  echo "  bcastMax  : ${BROADCAST_MAX}  dep-thresh: ${DEPENDENTS_THRESHOLD}"echo "  Output dir: ${OUTPUT_DIR}"
echo "================================"

mkdir -p "${OUTPUT_DIR}/slurm_logs"

cd "${GEM5_ROOT}"

python3 "${GEM5_ROOT}/configs/mast/invoke-run.py" \
    --benchmark-num  "${BENCHMARK_NUM}"  \
    --mode           simrun              \
    --simpoint-num   "${SIMPOINT_NUM}"   \
    --cpu-width      "${CPU_WIDTH}"      \
    --output-dir     "${OUTPUT_DIR}"     \
    --config         "${GEM5_CONFIG}"    \
    --iq-size        "${IQ_SIZE}"        \
    --lq-size              "${LQ_SIZE}"              \
    --sq-size              "${SQ_SIZE}"              \
    --broadcastMax         "${BROADCAST_MAX}"        \
    --dependentsThreshold  "${DEPENDENTS_THRESHOLD}"