#!/bin/bash
# One-time (or refresh) packaging of the python disk-image rootfs for use on
# compute nodes where guestmount/libguestfs is unavailable.
#
# Creates runs/disk-images/pyperf-rootfs.tar from a guestmounted image (or an
# existing live mount).  The perf-measurement SLURM job extracts this tar to
# node-local scratch and runs benchmarks under bwrap.
#
# Usage (run on a login node with guestmount working, or with PYPERF_MNT set
# to an existing mount):
#   ./prepare_pyperf_rootfs.sh [GEM5_ROOT]

set -euo pipefail

GEM5_ROOT="${1:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"
IMG="${GEM5_ROOT}/runs/disk-images/x86-ubuntu-python"
OUT_TAR="${GEM5_ROOT}/runs/disk-images/pyperf-rootfs.tar"
MNT="${PYPERF_MNT:-/tmp/pyperf-rootfs-pack-$$}"

export XDG_RUNTIME_DIR="/tmp/xdg-pack-$$"
export TMPDIR="/tmp"
mkdir -p "${XDG_RUNTIME_DIR}"

cleanup() {
    if [ -n "${MOUNTED_BY_US:-}" ] && mountpoint -q "${MNT}" 2>/dev/null; then
        guestunmount "${MNT}" 2>/dev/null || true
        rmdir "${MNT}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

if [ -n "${PYPERF_MNT:-}" ] && mountpoint -q "${PYPERF_MNT}" 2>/dev/null; then
    MNT="${PYPERF_MNT}"
    echo "Using existing mount: ${MNT}"
elif mountpoint -q /tmp/pyperf-valgrind-mnt-2265873 2>/dev/null; then
    MNT=/tmp/pyperf-valgrind-mnt-2265873
    echo "Using existing mount: ${MNT}"
else
    export LIBGUESTFS_BACKEND=direct
    mkdir -p "${MNT}"
    guestmount -a "${IMG}" -m /dev/sda2 "${MNT}"
    MOUNTED_BY_US=1
    echo "Mounted ${IMG} at ${MNT}"
fi

echo "Packing rootfs -> ${OUT_TAR} (this may take several minutes)..."
tar -C "${MNT}" \
    --exclude=./dev \
    --exclude=./proc \
    --exclude=./sys \
    --exclude=./tmp \
    --exclude=./run \
    -cf "${OUT_TAR}" .

echo "Done: $(ls -lh "${OUT_TAR}")"
