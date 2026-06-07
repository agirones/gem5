#!/bin/bash
# Measure native dynamic instructions for each pyperformance benchmark using
# perf stat, running the same command as the gem5 guest workload inside a
# bwrap sandbox rooted at the python disk image.
#
# Requires runs/disk-images/pyperf-rootfs.tar (create with prepare_pyperf_rootfs.sh
# on a login node).  Compute nodes cannot use guestmount/libguestfs.
#
# Output: runs/output/micro26/rebuttal/pyperf/instr_count/perf_instructions.csv
#
# Usage:
#   ./measure_perf_instructions.sh [GEM5_ROOT]

set -euo pipefail

GEM5_ROOT="${1:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
BENCH_LIST="${GEM5_ROOT}/configs/mast/pyperf-benchmarks.txt"
ROOTFS_TAR="${GEM5_ROOT}/runs/disk-images/pyperf-rootfs.tar"
OUT_DIR="${GEM5_ROOT}/runs/output/micro26/rebuttal/pyperf/instr_count"
LOG_DIR="${OUT_DIR}/perf_logs"
CSV="${OUT_DIR}/perf_instructions.csv"
EXTRACT_DIR="${SLURM_TMPDIR:-/tmp}/pyperf-rootfs-${SLURM_JOB_ID:-$$}"
TIMEOUT_SEC="${PYPERF_PERF_TIMEOUT:-3600}"

# Compute nodes often have no writable /run/user/$UID (no systemd user session).
export XDG_RUNTIME_DIR="/tmp/xdg-perf-${SLURM_JOB_ID:-$$}"
export TMPDIR="/tmp"
mkdir -p "${XDG_RUNTIME_DIR}" "${OUT_DIR}" "${LOG_DIR}"

if [ ! -f "${ROOTFS_TAR}" ]; then
    echo "ERROR: ${ROOTFS_TAR} not found." >&2
    echo "Run prepare_pyperf_rootfs.sh on a login node first." >&2
    exit 1
fi

echo "Extracting rootfs tar to ${EXTRACT_DIR} ..."
mkdir -p "${EXTRACT_DIR}"
tar -xf "${ROOTFS_TAR}" -C "${EXTRACT_DIR}"
# The tar excludes volatile dirs (tmp/proc/dev/run/sys).  bwrap needs them to
# exist as mount points before it can bind /tmp or mount /proc on a ro-bind /.
for d in tmp proc dev run sys; do
    mkdir -p "${EXTRACT_DIR}/${d}"
done
chmod 1777 "${EXTRACT_DIR}/tmp"
echo "Rootfs ready."

echo "benchmark,instructions,status,elapsed_sec" > "${CSV}"

run_one() {
    local bench="$1"
    local log="${LOG_DIR}/${bench}.log"
    local t0 t1 elapsed rc inst status

    echo "=== ${bench} ==="
    t0=$(date +%s)
    set +e
    timeout "${TIMEOUT_SEC}" perf stat -e instructions \
        bwrap --ro-bind "${EXTRACT_DIR}" / \
              --bind /tmp /tmp \
              --proc /proc \
              --dev /dev \
              --tmpfs /run \
              --setenv XDG_RUNTIME_DIR /tmp \
              --setenv TMPDIR /tmp \
              --setenv HOME /home/gem5 \
              --chdir /home/gem5/pyperf \
              ./tool-venv/bin/python -m pyperformance run -b "${bench}" \
                  -o "/tmp/pyperf_perf_${bench}.json" \
        &> "${log}"
    rc=$?
    set -e
    t1=$(date +%s)
    elapsed=$((t1 - t0))

    inst=$(rg -o '[0-9,]+[[:space:]]+instructions' "${log}" 2>/dev/null | tail -1 | rg -o '^[0-9,]+' | tr -d ',' || true)
    if grep -q 'bwrap: ' "${log}" 2>/dev/null; then
        status=failed
        inst=""
    elif [ "${rc}" -eq 0 ] && [ -n "${inst}" ]; then
        status=ok
    elif [ "${rc}" -eq 124 ]; then
        status=timeout
        inst=""
    else
        status=failed
        inst=""
    fi

    echo "${bench},${inst},${status},${elapsed}" >> "${CSV}"
    echo "  -> ${status}  instructions=${inst:-n/a}  elapsed=${elapsed}s"
}

while read -r bench; do
    [[ -z "${bench}" || "${bench}" == \#* ]] && continue
    run_one "${bench}"
done < "${BENCH_LIST}"

echo "Wrote ${CSV}"
