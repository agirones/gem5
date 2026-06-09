#!/bin/bash
# Run pyperformance ffrun jobs for baseline and/or Sereno across the full
# pyperf benchmark list (configs/mast/pyperf-benchmarks.txt, 97 benchmarks).
#
# Uses git worktrees so baseline and Sereno jobs can run in parallel:
#   baseline : gem5-NTNU-baseline  (broadcastMax=12, dependentsThreshold=-1)
#   sereno   : gem5-NTNU-sereno    (broadcastMax=1,  dependentsThreshold=2)
#
# Post-boot checkpoints are shared: one ffcpt job per benchmark (if missing),
# installed to GEM5_POSTBOOT_CPTS on the main repo. ffrun jobs for each
# implementation depend on that checkpoint when it is newly created.
#
# Output tree (invoke-run width layout):
#   runs/output/micro26/rebuttal/pyperf/{baseline,sereno}/
#     width8/<bench>/m5out/stats.txt
#     slurm_logs/{ffcpt,ffrun}_<bench>.{out,err}
#
# Usage:
#   ./run_experiment.sh [baseline|sereno|both] [MAIN_GEM5_ROOT]
#
# Examples:
#   ./run_experiment.sh                         # both impls, all benchmarks
#   ./run_experiment.sh baseline                # baseline only
#   ./run_experiment.sh sereno                  # sereno only
#   BENCHMARK_INDICES="40 54" ./run_experiment.sh both

set -euo pipefail

IMPL="${1:-both}"
MAIN_ROOT="${2:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
EECS_ROOT="$(dirname "${MAIN_ROOT}")"

BASELINE_ROOT="${BASELINE_ROOT:-${EECS_ROOT}/gem5-NTNU-baseline}"
SERENO_ROOT="${SERENO_ROOT:-${EECS_ROOT}/gem5-NTNU-sereno}"

export GEM5_BENCH_SET=pyperf
export GEM5_DISK="${GEM5_DISK:-${MAIN_ROOT}/runs/disk-images/x86-ubuntu-python}"
export GEM5_POSTBOOT_CPTS="${GEM5_POSTBOOT_CPTS:-${MAIN_ROOT}/runs/legacy-checkpoints}"

CPU_WIDTH=8
FAST_FORWARD_LENGTH="${FAST_FORWARD_LENGTH:-10000000000}"
WARMUP_LENGTH="${WARMUP_LENGTH:-50000000}"
MEASURE_LENGTH="${MEASURE_LENGTH:-200000000}"

SENS_BASE="${MAIN_ROOT}/runs/output/micro26/rebuttal/pyperf"
CPT_OUTPUT_DIR="${SENS_BASE}/_cpt_gen"
FFCPT_SCRIPT="${MAIN_ROOT}/slurm/single_ffcpt_job.slurm"
FFRUN_SCRIPT="${MAIN_ROOT}/slurm/single_ffrun_job.slurm"

declare -A IMPL_PARAMS=(
    [baseline]="12 -1"
    [sereno]="1 2"
)
declare -A IMPL_ROOT=(
    [baseline]="${BASELINE_ROOT}"
    [sereno]="${SERENO_ROOT}"
)

case "${IMPL}" in
    baseline|sereno|both) ;;
    *)
        echo "Usage: $0 [baseline|sereno|both] [MAIN_GEM5_ROOT]" >&2
        exit 1
        ;;
esac

if [ -n "${BENCHMARK_INDICES:-}" ]; then
    # shellcheck disable=SC2206
    INDICES=(${BENCHMARK_INDICES})
else
    mapfile -t INDICES < <(GEM5_BENCH_SET=pyperf python3 -c "
import sys
sys.path.insert(0, '${MAIN_ROOT}/configs/mast')
from benchmarks import ALL_BENCHMARKS
for i in range(len(ALL_BENCHMARKS)):
    print(i)
")
fi

mkdir -p "${CPT_OUTPUT_DIR}/slurm_logs" "${GEM5_POSTBOOT_CPTS}"

echo "=== pyperformance ffrun submission (rebuttal) ==="
echo "  implementations     : ${IMPL}"
echo "  main repo           : ${MAIN_ROOT}"
echo "  baseline worktree   : ${BASELINE_ROOT}"
echo "  sereno worktree     : ${SERENO_ROOT}"
echo "  ff / warmup / meas  : ${FAST_FORWARD_LENGTH} / ${WARMUP_LENGTH} / ${MEASURE_LENGTH}"
echo "  disk                : ${GEM5_DISK}"
echo "  post-boot cpts      : ${GEM5_POSTBOOT_CPTS}"
echo "  output base         : ${SENS_BASE}"
echo "  benchmarks          : ${#INDICES[@]} indices"
echo ""

total_ffcpt=0
total_ffrun=0

submit_ffrun() {
    local impl="$1"
    local benchmark_num="$2"
    local bench_name="$3"
    local dep="$4"

    read -r broadcast_max dependents_threshold <<< "${IMPL_PARAMS[$impl]}"
    local gem5_root="${IMPL_ROOT[$impl]}"
    local output_dir="${SENS_BASE}/${impl}"

    mkdir -p "${output_dir}/slurm_logs"

    local run_jid
    run_jid=$(sbatch --parsable ${dep} \
        --export=ALL,\
BENCHMARK_NUM=${benchmark_num},\
CPU_WIDTH=${CPU_WIDTH},\
BROADCAST_MAX=${broadcast_max},\
DEPENDENTS_THRESHOLD=${dependents_threshold},\
FAST_FORWARD_LENGTH=${FAST_FORWARD_LENGTH},\
WARMUP_LENGTH=${WARMUP_LENGTH},\
MEASURE_LENGTH=${MEASURE_LENGTH},\
OUTPUT_DIR=${output_dir},\
GEM5_ROOT=${gem5_root},\
GEM5_BENCH_SET=pyperf,\
GEM5_DISK=${GEM5_DISK},\
GEM5_POSTBOOT_CPTS=${GEM5_POSTBOOT_CPTS} \
        --output="${output_dir}/slurm_logs/ffrun_${bench_name}.out" \
        --error="${output_dir}/slurm_logs/ffrun_${bench_name}.err" \
        "${FFRUN_SCRIPT}")
    echo "    [${impl}] ffrun job: ${run_jid}"
    total_ffrun=$((total_ffrun + 1))
}

for BENCHMARK_NUM in "${INDICES[@]}"; do
    BENCH_NAME=$(GEM5_BENCH_SET=pyperf python3 -c "
import sys
sys.path.insert(0, '${MAIN_ROOT}/configs/mast')
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
OUTPUT_DIR=${CPT_OUTPUT_DIR},\
GEM5_ROOT=${MAIN_ROOT},\
GEM5_BENCH_SET=pyperf,\
GEM5_DISK=${GEM5_DISK},\
GEM5_POSTBOOT_CPTS=${GEM5_POSTBOOT_CPTS} \
            --output="${CPT_OUTPUT_DIR}/slurm_logs/ffcpt_${BENCH_NAME}.out" \
            --error="${CPT_OUTPUT_DIR}/slurm_logs/ffcpt_${BENCH_NAME}.err" \
            "${FFCPT_SCRIPT}")
        echo "    ffcpt job: ${cpt_jid}"
        dep="--dependency=afterok:${cpt_jid}"
        total_ffcpt=$((total_ffcpt + 1))
    else
        echo "[${BENCHMARK_NUM} ${BENCH_NAME}] post-boot checkpoint exists"
    fi

    if [ "${IMPL}" = "both" ] || [ "${IMPL}" = "baseline" ]; then
        submit_ffrun baseline "${BENCHMARK_NUM}" "${BENCH_NAME}" "${dep}"
    fi
    if [ "${IMPL}" = "both" ] || [ "${IMPL}" = "sereno" ]; then
        submit_ffrun sereno "${BENCHMARK_NUM}" "${BENCH_NAME}" "${dep}"
    fi
done

echo ""
echo "Submitted ${total_ffcpt} ffcpt + ${total_ffrun} ffrun jobs."
echo "Stats: ${SENS_BASE}/{baseline,sereno}/width${CPU_WIDTH}/<bench>/m5out/stats.txt"
