#!/bin/bash
# Generate the post-boot checkpoint for a single benchmark, for use by the
# "ffrun" fast-forward workflow. Boots Linux from scratch in an atomic CPU and
# checkpoints at the run script's leading `m5 checkpoint` (just before the
# benchmark starts), then installs the checkpoint into GEM5_POSTBOOT_CPTS so
# ffrun can restore it.
#
# Required environment variables:
#   BENCHMARK_NUM   - index into ALL_BENCHMARKS (set matters: see GEM5_BENCH_SET)
#   CPU_WIDTH       - processor width (only used for the work-dir layout here)
#   OUTPUT_DIR      - base directory for simulation output / scratch
#   GEM5_ROOT       - path to the gem5 repository root
#
# Important environment variables:
#   GEM5_BENCH_SET       - "pyperf" to use the pyperformance suite (default)
#   GEM5_DISK            - disk image to boot (default: the python image)
#   GEM5_POSTBOOT_CPTS   - where to install <bench>-cpt (default: runs/legacy-checkpoints)
#   GEM5_CONFIG          - gem5 config (default: profile-config-legacy.py)

#SBATCH --job-name=gem5_ffcpt
#SBATCH --output=slurm_logs/ffcpt_%A_%a.out
#SBATCH --error=slurm_logs/ffcpt_%A_%a.err
#SBATCH --time=0-08:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=25GB

export LMOD_DISABLE_SAME_NAME_AUTOSWAP=no
module load Python/3.12.3-GCCcore-13.3.0

GEM5_ROOT="${GEM5_ROOT:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
GEM5_CONFIG="${GEM5_CONFIG:-${GEM5_ROOT}/configs/mast/profile-config-legacy.py}"
CPU_WIDTH="${CPU_WIDTH:-8}"

export GEM5_BENCH_SET="${GEM5_BENCH_SET:-pyperf}"
export GEM5_DISK="${GEM5_DISK:-${GEM5_ROOT}/runs/disk-images/x86-ubuntu-python}"
export GEM5_POSTBOOT_CPTS="${GEM5_POSTBOOT_CPTS:-${GEM5_ROOT}/runs/legacy-checkpoints}"

SIF="${GEM5_ROOT}/mast_gem5.sif"

# Resolve the benchmark name for the selected suite + index.
NAME=$(GEM5_BENCH_SET="${GEM5_BENCH_SET}" python3 -c "
import sys
sys.path.insert(0, '${GEM5_ROOT}/configs/mast')
from benchmarks import ALL_BENCHMARKS
print(ALL_BENCHMARKS[${BENCHMARK_NUM}].name)
")

WORKDIR="${OUTPUT_DIR}/width${CPU_WIDTH}/${NAME}"
GENDIR="${WORKDIR}/cpt_gen"
mkdir -p "${WORKDIR}" "${GENDIR}" "${OUTPUT_DIR}/slurm_logs"

echo "=== gem5 post-boot checkpoint (cpt) job ==="
echo "  Benchmark : ${BENCHMARK_NUM} (${NAME})"
echo "  Bench set : ${GEM5_BENCH_SET}"
echo "  Disk      : ${GEM5_DISK}"
echo "  Gen dir   : ${GENDIR}"
echo "  Install to: ${GEM5_POSTBOOT_CPTS}/${NAME}-cpt"
echo "==========================================="

cd "${GEM5_ROOT}"

apptainer exec -B /cluster:/cluster \
    --env GEM5_BENCH_SET="${GEM5_BENCH_SET}" \
    --env GEM5_DISK="${GEM5_DISK}" \
    "${SIF}" \
    "${GEM5_ROOT}/build/X86/gem5.opt" -d "${GENDIR}" \
    "${GEM5_CONFIG}" \
    --benchmark-num "${BENCHMARK_NUM}" \
    --mode cpt \
    --cpu-width "${CPU_WIDTH}" \
    --run-base-dir "${OUTPUT_DIR}"

if [ ! -d "${GENDIR}/${NAME}-cpt" ]; then
    echo "ERROR: checkpoint ${GENDIR}/${NAME}-cpt was not created." >&2
    exit 1
fi

mkdir -p "${GEM5_POSTBOOT_CPTS}"
rm -rf "${GEM5_POSTBOOT_CPTS}/${NAME}-cpt"
cp -a "${GENDIR}/${NAME}-cpt" "${GEM5_POSTBOOT_CPTS}/${NAME}-cpt"
echo "Installed post-boot checkpoint -> ${GEM5_POSTBOOT_CPTS}/${NAME}-cpt"
