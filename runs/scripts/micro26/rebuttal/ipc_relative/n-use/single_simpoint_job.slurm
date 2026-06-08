#!/bin/bash
# N-use variant of single_simpoint_job.slurm — forwards I-buffer / N-use
# parameters to invoke-run.py (required on the n-use/InO branch).
#
# All parameters are passed via --export in the sbatch invocation.

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

CORE_SCALE="${CORE_SCALE:-1.0}"
IQ_SIZE="${IQ_SIZE:-256}"
LQ_SIZE="${LQ_SIZE:-256}"
SQ_SIZE="${SQ_SIZE:-256}"
N_SLOTS="${N_SLOTS:-2}"
I_BUFFER_SIZE="${I_BUFFER_SIZE:-32}"
I_BUFFER_HEAD="${I_BUFFER_HEAD:-1}"
BROADCAST_MAX="${BROADCAST_MAX:-12}"
DEPENDENTS_THRESHOLD="${DEPENDENTS_THRESHOLD:--1}"
L1_LATENCY="${L1_LATENCY:-1}"
WARMUP_LENGTH="${WARMUP_LENGTH:--1}"
FAST_FORWARD_LENGTH="${FAST_FORWARD_LENGTH:-0}"

echo "=== gem5 single-simpoint job (n-use) ==="
echo "  Job ID    : ${SLURM_JOB_ID}"
echo "  Benchmark : ${BENCHMARK_NUM}"
echo "  Simpoint  : ${SIMPOINT_NUM}"
echo "  CPU width : ${CPU_WIDTH}"
echo "  n-slots   : ${N_SLOTS}  i-buffer-head: ${I_BUFFER_HEAD}"
echo "  L1 latency: ${L1_LATENCY}"
echo "  warmup    : ${WARMUP_LENGTH}  fast-fwd: ${FAST_FORWARD_LENGTH}"
echo "  Output dir: ${OUTPUT_DIR}"
echo "========================================"

mkdir -p "${OUTPUT_DIR}/slurm_logs"

cd "${GEM5_ROOT}"

python3 "${GEM5_ROOT}/configs/mast/invoke-run.py" \
    --benchmark-num  "${BENCHMARK_NUM}"  \
    --mode           simrun              \
    --simpoint-num   "${SIMPOINT_NUM}"   \
    --cpu-width      "${CPU_WIDTH}"      \
    --core-scale     "${CORE_SCALE}"     \
    --output-dir     "${OUTPUT_DIR}"     \
    --config         "${GEM5_CONFIG}"    \
    --iq-size        "${IQ_SIZE}"        \
    --lq-size              "${LQ_SIZE}"              \
    --sq-size              "${SQ_SIZE}"              \
    --n-slots              "${N_SLOTS}"              \
    --i-buffer-size        "${I_BUFFER_SIZE}"        \
    --i-buffer-head        "${I_BUFFER_HEAD}"        \
    --broadcastMax         "${BROADCAST_MAX}"        \
    --dependentsThreshold  "${DEPENDENTS_THRESHOLD}" \
    --l1-latency           "${L1_LATENCY}"           \
    --warmup-length        "${WARMUP_LENGTH}"        \
    --fast-forward-length  "${FAST_FORWARD_LENGTH}"
