# Native instruction counts for pyperformance benchmarks

This note describes the two scripts that estimate how many **dynamic x86
instructions** each pyperformance benchmark executes, using Linux `perf` on real
hardware. The counts are useful for comparing benchmark length and tuning
`FAST_FORWARD_LENGTH` in gem5; they are **not** gem5 `simInsts`.

## The problem these scripts solve

pyperformance is installed inside the gem5 disk image
(`runs/disk-images/x86-ubuntu-python`), not on the cluster host. Inside the
guest, each benchmark is launched as:

```bash
cd /home/gem5/pyperf
./tool-venv/bin/python -m pyperformance run -b <name> -o /tmp/out.json
```

That Python binary needs the **guest Ubuntu root filesystem** (`/usr`, `/lib64`,
…). You cannot run it directly on the host (wrong glibc).

To count instructions with `perf stat -e instructions`, we must run that command
in an environment that looks like the guest OS:

| Location | Mount disk image? |
|---|---|
| Login node | Yes — `guestmount` works |
| Compute node | **No** — libguestfs / `guestmount` crashes on SLURM nodes |

The workflow is therefore split: **pack the guest root once on a login node**,
then **measure on compute nodes** from that archive.

---

## Overview

```
prepare_pyperf_rootfs.sh          measure_perf_instructions.sh
   (login node, once)                 (compute node / SLURM)

x86-ubuntu-python                      pyperf-rootfs.tar
        │ guestmount                          │ tar -xf
        ▼                                     ▼
   mounted rootfs  ──tar──►  pyperf-rootfs.tar ──►  bwrap + perf stat
                                                          │
                                                          ▼
                                               perf_instructions.csv
```

---

## 1. `prepare_pyperf_rootfs.sh` — one-time packaging

**Where to run:** login node (or anywhere `guestmount` works).

**Purpose:** Copy the guest OS out of the disk image into a portable tar so
compute nodes never need libguestfs.

**Steps:**

1. Mount `runs/disk-images/x86-ubuntu-python` with `guestmount` on `/dev/sda2`,
   or reuse an existing mount (`PYPERF_MNT` or `/tmp/pyperf-valgrind-mnt-*`).
2. Archive almost the full guest root into `runs/disk-images/pyperf-rootfs.tar`
   (~6.5 GB).
3. Exclude volatile directories that should not be archived: `dev`, `proc`,
   `sys`, `tmp`, `run`.

**Usage:**

```bash
./runs/scripts/micro26/rebuttal/pyperf/prepare_pyperf_rootfs.sh

# Or, if you already have a live guestmount:
PYPERF_MNT=/path/to/mount ./runs/scripts/micro26/rebuttal/pyperf/prepare_pyperf_rootfs.sh
```

**When to re-run:** only after changing the disk image (new pyperformance deps,
Python packages, etc.).

**Output:** `runs/disk-images/pyperf-rootfs.tar`

---

## 2. `measure_perf_instructions.sh` — count instructions for all benchmarks

**Where to run:** compute node (typically via SLURM). Requires the tar from
step 1.

**Purpose:** For every benchmark in `configs/mast/pyperf-benchmarks.txt`, run
the same command gem5 uses and record the total `perf` instruction count.

**Steps:**

1. Extract `pyperf-rootfs.tar` to node-local scratch:
   `$SLURM_TMPDIR/pyperf-rootfs-<jobid>`.
2. Create empty mount-point directories (`tmp`, `proc`, `dev`, `run`, `sys`).
   The tar omits them; `bwrap` needs them before it can bind `/tmp` or mount
   `/proc` on a read-only root.
3. For each benchmark name in `pyperf-benchmarks.txt`:
   - Wrap execution in `bwrap` with the extracted tree as read-only `/`.
   - Run `perf stat -e instructions` on:
     ```bash
     ./tool-venv/bin/python -m pyperformance run -b <bench> -o /tmp/pyperf_perf_<bench>.json
     ```
   - Parse the `instructions:` total from perf output.
   - Append one row to a CSV (`ok`, `failed`, or `timeout`).

**Usage:**

```bash
./runs/scripts/micro26/rebuttal/pyperf/measure_perf_instructions.sh
```

**SLURM example:**

```bash
sbatch --job-name=pyperf_perf --time=2-00:00:00 --cpus-per-task=1 --mem=8GB \
  --output=runs/output/micro26/rebuttal/pyperf/instr_count/slurm_perf.out \
  --error=runs/output/micro26/rebuttal/pyperf/instr_count/slurm_perf.err \
  --wrap='runs/scripts/micro26/rebuttal/pyperf/measure_perf_instructions.sh'
```

**Outputs:**

| Path | Contents |
|---|---|
| `runs/output/micro26/rebuttal/pyperf/instr_count/perf_instructions.csv` | `benchmark,instructions,status,elapsed_sec` |
| `runs/output/micro26/rebuttal/pyperf/instr_count/perf_logs/<bench>.log` | Full perf + pyperformance log per benchmark |

**Optional environment variables:**

| Variable | Default | Meaning |
|---|---|---|
| `PYPERF_PERF_TIMEOUT` | `3600` | Per-benchmark timeout (seconds) |
| `SLURM_TMPDIR` | `/tmp` | Where the rootfs tar is extracted |

---

## What the numbers mean

- **Source:** hardware performance counter (`instructions`), user-space only
  (`instructions:u` in perf output).
- **Scope:** the entire `pyperformance run` invocation — venv checks, harness
  overhead, and multiple timed iterations (not a single gem5 measured region).
- **Use:** compare relative benchmark length; choose `FAST_FORWARD_LENGTH` for
  gem5 `ffrun`.
- **Limitation:** native x86 count ≠ gem5 full-system `simInsts` (no simulated
  kernel, different timing, etc.).

For **exact** gem5 instruction totals from the post-boot checkpoint to benchmark
end, use gem5 atomic simulation (e.g. `--mode profile`) instead of `perf`.

---

## Known pitfalls (already hit in this workflow)

1. **`XDG_RUNTIME_DIR=/run/user/$UID`** on compute nodes is not writable.
   The measure script forces `XDG_RUNTIME_DIR=/tmp/xdg-perf-<jobid>`.
2. **`guestmount` on compute nodes** fails (libguestfs appliance crash). Use
   the tar + extract path instead.
3. **Missing `/tmp` in the tar** caused `bwrap: Can't mkdir /tmp: Read-only
   file system`. Fixed by creating `tmp/`, `proc/`, `dev/`, `run/`, `sys/`
   after extraction.
4. **Network benchmarks** (`asyncio_*`, `tornado_http`, `fastapi`, …) may
   fail offline inside `bwrap` even when CPU-bound benchmarks succeed.

---

## Quick reference

| Script | Run where | Produces |
|---|---|---|
| `prepare_pyperf_rootfs.sh` | Login node | `runs/disk-images/pyperf-rootfs.tar` |
| `measure_perf_instructions.sh` | Compute / SLURM | `perf_instructions.csv` + logs |
