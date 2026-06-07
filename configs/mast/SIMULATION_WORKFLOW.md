# gem5 Simulation & Checkpoint Workflow (SPEC CPU2017 + Python / pyperformance)

This document describes, end to end, how full-system gem5 simulations and
checkpoints are produced in this repository for two benchmark suites:

- **SPEC CPU2017** — the established SimPoint-based methodology.
- **Python / pyperformance** — a fast-forward ("ffrun") methodology added for
  running real Python workloads.

Both flows share the same gem5 config (`profile-config-legacy.py`), the same
front-end (`invoke-run.py`), and the same Apptainer container; they differ in
*how the measured region is selected* (SimPoint clustering vs. a fixed
fast-forward distance) and in *which disk image* they boot.

---

## 1. Components & key paths

| Component | Path |
|---|---|
| gem5 repo root | `/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU` |
| gem5 binary | `build/X86/gem5.opt` (`gem5.debug` for GDB) |
| Apptainer image | `mast_gem5.sif` |
| gem5 config script | `configs/mast/profile-config-legacy.py` |
| Run front-end | `configs/mast/invoke-run.py` |
| Benchmark registry | `configs/mast/benchmarks.py` |
| SPEC17 list | `configs/mast/spec17-benchmarks.txt` |
| pyperformance list | `configs/mast/pyperf-benchmarks.txt` |
| SPEC17 disk image | `/cluster/projects/mast/full-system/disk-images/x86-ubuntu-with-spec17` |
| Python disk image | `runs/disk-images/x86-ubuntu-python` |

### Shared storage (artifacts)

| Artifact | Default location | Env override |
|---|---|---|
| Post-boot checkpoints | `runs/legacy-checkpoints/<bench>-cpt` | `GEM5_POSTBOOT_CPTS` |
| SimPoint BBV inputs | `/cluster/projects/mast/simpoints/bbv-analysis/<bench>.bb.gz` | — |
| SimPoint clusters | `/cluster/projects/mast/simpoints/simpoints/<bench>.{simpoints,weights}` | — |
| SimPoint checkpoints | `/cluster/projects/mast/checkpoints/simpoint-checkpoints/<bench>/cpt.*` | `GEM5_CPTS` |

### Environment variables that steer a run

| Variable | Meaning | Default |
|---|---|---|
| `GEM5_BENCH_SET` | which benchmark list to load: `spec` or `pyperf` | `spec` |
| `GEM5_DISK` | disk image to boot | SPEC17 image |
| `GEM5_KERNEL` | kernel binary | repo default |
| `GEM5_POSTBOOT_CPTS` | post-boot checkpoint dir | `runs/legacy-checkpoints` |
| `GEM5_CPTS` | SimPoint checkpoint dir | `/cluster/projects/mast/checkpoints/simpoint-checkpoints` |
| `GEM5_ROOT` | repo root | hard-coded fallback |

> `benchmarks.py` reads `GEM5_BENCH_SET` to decide whether `ALL_BENCHMARKS` is
> populated from `spec17-benchmarks.txt` (`kind="spec"`) or
> `pyperf-benchmarks.txt` (`kind="pyperf"`). The index passed as
> `--benchmark-num` is an index into that list, so **the same number means
> different benchmarks depending on `GEM5_BENCH_SET`**.

---

## 2. The five gem5 operation modes

`profile-config-legacy.py` selects behaviour from `--mode`:

| Mode | CPU(s) | What it does | Used by |
|---|---|---|---|
| `cpt` | Atomic | Boot Linux, run `after_boot.sh` to the first `m5 checkpoint`, save a **post-boot checkpoint** (`<bench>-cpt`). | both suites |
| `profile` | Atomic | Restore post-boot cpt, run the benchmark with a SimPoint BBV probe (`addSimPointProbe`, 50M interval) to emit `simpoint.bb.gz`. | SPEC17 |
| `simtake` | Atomic | Restore post-boot cpt, replay to each SimPoint start and write a **SimPoint checkpoint** per cluster. | SPEC17 |
| `simrun` | O3 (opt. Atomic FF) | Restore a SimPoint checkpoint, warm up, then **measure** one 50M interval in detailed O3. | SPEC17 |
| `ffrun` | Atomic → O3 | Restore the post-boot cpt, **fast-forward** N insts in Atomic, switch to O3, warm up, then **measure** a fixed region. | Python |

Key control constants (in `profile-config-legacy.py`):

- `simpoint_interval = 50_000_000` (SPEC measured interval, baked into cpt names)
- `warmup_length` default `10_000_000` (overridable via `--warmup-length`)
- `ffrun` measured region: `--measure-length` (default `100_000_000`)
- `ffrun` warmup: `--warmup-length` (default `50_000_000` in the slurm script)
- `ffrun` fast-forward: `--fast-forward-length`

`--warmup-length = -1` (the SimPoint slurm default) means "read the warmup
length from the checkpoint name".

---

## 3. SPEC CPU2017 workflow (SimPoint methodology)

This is the multi-stage pipeline that turns a benchmark into a small set of
weighted, representative O3 measurements.

```
[cpt]  boot ───────────────► post-boot checkpoint  (runs/legacy-checkpoints/<b>-cpt)
                                   │
[profile]  restore + BBV probe ────┘──► simpoint.bb.gz  ──► copy_bbv.py
                                                              │
                                          (external) SimPoint clustering tool
                                                              │
                                          <b>.simpoints + <b>.weights
                                                              │
[simtake]  restore + replay to each SimPoint ──► per-cluster SimPoint checkpoints
                                                              │
[simrun]  restore each SimPoint cpt ──► O3 warmup + 50M measured region ──► stats.txt
                                                              │
                                       weighted-average IPC/etc. across SimPoints
```

### Stage 1 — Post-boot checkpoint (`cpt`)
Boots Linux in the Atomic CPU and stops at the leading `m5 checkpoint` in
`after_boot.sh` (just before the benchmark binary would launch). The checkpoint
is written as `<bench>-cpt`. Copy it into the shared post-boot location with
`runs/copy_checkpoints.py`.

### Stage 2 — BBV profile (`profile`)
Restores the post-boot checkpoint and runs the whole benchmark in Atomic with a
SimPoint probe at a 50M-instruction interval. gem5 emits a basic-block vector
(`simpoint.bb.gz`). `runs/copy_bbv.py` copies these to
`/cluster/projects/mast/simpoints/bbv-analysis/`.

### Stage 3 — SimPoint clustering (external)
The standard SimPoint tool clusters the BBVs into representative intervals,
producing `<bench>.simpoints` and `<bench>.weights` under
`/cluster/projects/mast/simpoints/simpoints/`. `parseSimpoints()` in the config
reads these in the next stages.

### Stage 4 — SimPoint checkpoints (`simtake`)
Restores the post-boot checkpoint and replays in Atomic, writing one checkpoint
per SimPoint. Checkpoint names encode everything needed downstream:

```
cpt.simpoint_<idx>_inst_<startInst>_weight_<w>_interval_50000000_warmup_<wlen>
```

`runs/copy_simpoint_checkpoints.py` stages them under
`/cluster/projects/mast/checkpoints/simpoint-checkpoints/<bench>/`.

### Stage 5 — Detailed measurement (`simrun`)
Restores a single SimPoint checkpoint, warms up the O3 microarchitecture, then
measures exactly one 50M-instruction interval. Each SimPoint is an independent
gem5 run; the per-SimPoint stats are later combined using the SimPoint weights.

The interval length and warmup are parsed from the checkpoint name, so `simrun`
ignores `--measure-length`.

### Running SPEC17 on SLURM
One SLURM job per `(benchmark, simpoint)` pair:

```bash
sbatch --export=ALL,BENCHMARK_NUM=<b>,SIMPOINT_NUM=<s>,CPU_WIDTH=8,\
OUTPUT_DIR=$PWD/runs/output/spec17,GEM5_ROOT=$PWD \
  slurm/single_simpoint_job.slurm
```

`single_simpoint_job.slurm` calls `invoke-run.py --mode simrun` with the core
parameters (`--cpu-width`, `--core-scale`, `--iq-size`, `--lq-size`, `--sq-size`,
`--broadcastMax`, `--dependentsThreshold`, `--l1-latency`, `--warmup-length`,
`--fast-forward-length`). It defaults `WARMUP_LENGTH=-1` (read from the
checkpoint) and `FAST_FORWARD_LENGTH=0` (no extra Atomic skip).

---

## 4. Python / pyperformance workflow (fast-forward "ffrun")

pyperformance benchmarks are interpreter workloads with no SimPoint clusters and
relatively short total instruction counts, so they use a **single fixed
fast-forward** instead of SimPoint clustering:

```
[ffcpt = cpt]  boot python image ──► post-boot checkpoint (<bench>-cpt)
                                          │
[ffrun]  restore cpt
           ├─ Atomic: fast-forward  FAST_FORWARD_LENGTH insts   (skip Python startup)
           ├─ switch Atomic → O3, flush caches/TLBs
           ├─ O3: warm up  WARMUP_LENGTH insts
           └─ O3: measure  MEASURE_LENGTH insts ──► stats.txt
```

### 4.1 FAQ: which benchmarks, why a checkpoint, where results land

**Which pyperformance benchmarks run?**
Any name listed in `configs/mast/pyperf-benchmarks.txt` (97 benchmarks, all
pre-installed in the image). You pick them by *index* via `--benchmark-num`
(0-based, counting only non-comment lines). The driver
`run_pyperf_ffrun.sh` runs a **default CPU-bound subset** when given no
arguments:

| Index | Benchmark | Why it's in the default set |
|---|---|---|
| 40 | `float` | pure FP math, deterministic |
| 54 | `nbody` | FP physics loop |
| 26 | `chaos` | integer/FP fractal |
| 45 | `go` | AI/search, branchy integer |
| 74 | `richards` | classic OS-scheduler kernel |

These are the most natural fit for single-core, full-system gem5. The
`async_*`, `asyncio_*`, `tornado_http`, `fastapi`, and `networkx` benchmarks are
event-loop / networking workloads that can behave oddly under gem5 and are best
avoided unless you specifically need them.

**List the benchmarks and their indices:**
```bash
GEM5_BENCH_SET=pyperf python3 -c "
import sys; sys.path.insert(0,'configs/mast')
from benchmarks import ALL_BENCHMARKS as B
for i,b in enumerate(B): print(i, b.name)"
```

**Why take a checkpoint at all?**
Booting the 16 GiB full-system Linux image and starting Python takes ~30 min of
simulation *every time* (and must run on a compute node). The post-boot
checkpoint captures the machine state **right after boot, paused at the line
just before the benchmark launches**. Every measurement (`ffrun`) then *restores*
that state in seconds instead of re-booting. So you boot **once per benchmark**
and can reuse that checkpoint for **many** detailed runs (different CPU widths,
cache latencies, IQ sizes, etc.) — that is the whole point of the two-stage
`ffcpt` → `ffrun` split.

**Where are the results stored?**
For each run under `OUTPUT_DIR` (default `runs/output/pyperf/ffrun`):

| What | Path |
|---|---|
| **Detailed O3 stats** (the result you want) | `width<W>/<bench>/m5out/stats.txt` |
| Post-boot checkpoint (reusable) | `runs/legacy-checkpoints/<bench>-cpt` and the scratch copy in `width<W>/<bench>/cpt_gen/<bench>-cpt` |
| SLURM logs | `slurm_logs/{ffcpt,ffrun}_<bench>.{out,err}` |
| Config snapshot | `width<W>/<bench>/m5out/config.{ini,json}` |

`stats.txt` contains **two stat dumps**: the first is the end-of-warmup snapshot
(FF + warmup instructions, then reset), and the second is the **measured region**
(exactly `MEASURE_LENGTH` instructions) — that second block is the one to read
(`system.switch_cpus.ipc`, `.cpi`, `.numCycles`, etc.). Note the
`pyperformance` JSON (`result_<bench>.json`) is written *inside the guest disk*
and is not auto-extracted; the gem5 `stats.txt` is the microarchitectural result.

### 4.2 The Python disk image (`x86-ubuntu-python`)
Built once by copying the SPEC17 image and injecting, fully offline:

- `pip`, `venv`/`ensurepip` (extracted from the `python3-pip`,
  `python3.12-venv` debs).
- Python dev headers + toolchain (`python3.12-dev`, `libpython3.12-dev`,
  `zlib1g-dev`, `libexpat1-dev`, `libstdc++-13-dev`, gcc) so C extensions build.
- The full **pyperformance** suite pre-installed under `/home/gem5/pyperf`,
  with every benchmark's dependencies baked into a shared venv
  (`pyperformance venv create -b all`) so no network is needed at run time.

The injection used `guestmount` + `bwrap` (UID-mapped to the guest `gem5` user)
to install on fast local disk, then `guestfish tar-in` to bulk-load the tree
with correct `gem5:gem5` ownership. (Build notes are captured in this repo's
chat history; the image itself is the deliverable.)

### 4.3 Guest run command
For `kind="pyperf"` benchmarks, `profile-config-legacy.py` injects this guest
script (the leading `m5 checkpoint` is where `cpt`/`ffcpt` stops):

```sh
m5 checkpoint
cd /home/gem5/pyperf
./tool-venv/bin/python -m pyperformance run -b <bench> \
    -o /home/gem5/pyperf/result_<bench>.json
m5 exit
```

### 4.4 Stage A — Post-boot checkpoint (`single_ffcpt_job.slurm`)
Runs gem5 `--mode cpt` on the Python image and installs the result to
`GEM5_POSTBOOT_CPTS/<bench>-cpt`. Defaults: `GEM5_BENCH_SET=pyperf`,
`GEM5_DISK=runs/disk-images/x86-ubuntu-python`.

### 4.5 Stage B — Fast-forward measurement (`single_ffrun_job.slurm`)
Runs `invoke-run.py --mode ffrun`. Defaults tuned for Python:

| Param | Default | Notes |
|---|---|---|
| `FAST_FORWARD_LENGTH` | `2_000_000_000` (2B) | clears Python startup, lands in steady state |
| `WARMUP_LENGTH` | `50_000_000` (50M) | O3 warmup |
| `MEASURE_LENGTH` | `100_000_000` (100M) | O3 measured region |
| `CPU_WIDTH` | `8` | — |

> **Tuning the fast-forward.** A SPEC-style 100B skip is wrong for
> pyperformance: it overshoots (the benchmark exits before the measured region)
> and is needlessly slow in Atomic. If a run logs *"Benchmark exited during
> fast-forward"*, **reduce** `FAST_FORWARD_LENGTH`. For long workloads run via
> `ffrun`, increase it.

### 4.6 Driver — `runs/scripts/pyperf/run_pyperf_ffrun.sh`
Submits the whole pipeline with SLURM dependencies. For each benchmark index:

1. If `GEM5_POSTBOOT_CPTS/<bench>-cpt` is missing, submit `single_ffcpt_job.slurm`.
2. Submit `single_ffrun_job.slurm` with `--dependency=afterok:<cpt_jid>`
   (so the measurement waits for a successful checkpoint).

```bash
# Default CPU-bound subset (float, nbody, chaos, go, richards):
./runs/scripts/pyperf/run_pyperf_ffrun.sh

# Specific indices into pyperf-benchmarks.txt:
./runs/scripts/pyperf/run_pyperf_ffrun.sh 40 54 26
```

Output tree:

```
runs/output/pyperf/ffrun/
  width8/<bench>/m5out/stats.txt      # detailed O3 measurement
  slurm_logs/{ffcpt,ffrun}_<bench>.{out,err}
runs/legacy-checkpoints/<bench>-cpt   # post-boot checkpoints
```

---

## 5. How the front-end ties it together

`invoke-run.py` is the single entry point for both suites. It:

1. Looks up the benchmark by `--benchmark-num` (in the `GEM5_BENCH_SET` list).
2. Creates the per-run work dir `OUTPUT_DIR/width<W>/<bench>`.
3. Builds an `apptainer exec -B /cluster:/cluster ...` command, **forwarding the
   `GEM5_*` environment** into the container with `--env`, and invokes
   `gem5.opt <config> --mode <mode> ...`.
4. For `--mode ffrun` it additionally forwards `--measure-length`.

This is why every mode is reproducible from the same container with only env
vars + CLI flags changing.

---

## 6. Quick reference

### Generate a post-boot checkpoint (either suite)
```bash
# Python example (index into pyperf list)
sbatch --export=ALL,BENCHMARK_NUM=40,CPU_WIDTH=8,\
OUTPUT_DIR=$PWD/runs/output/pyperf/ffrun,GEM5_ROOT=$PWD,GEM5_BENCH_SET=pyperf,\
GEM5_DISK=$PWD/runs/disk-images/x86-ubuntu-python \
  slurm/single_ffcpt_job.slurm
```

### Run one Python measurement (after the checkpoint exists)
```bash
sbatch --export=ALL,BENCHMARK_NUM=40,CPU_WIDTH=8,\
OUTPUT_DIR=$PWD/runs/output/pyperf/ffrun,GEM5_ROOT=$PWD,GEM5_BENCH_SET=pyperf,\
FAST_FORWARD_LENGTH=2000000000,WARMUP_LENGTH=50000000,MEASURE_LENGTH=100000000 \
  slurm/single_ffrun_job.slurm
```

### Run one SPEC17 SimPoint
```bash
sbatch --export=ALL,BENCHMARK_NUM=0,SIMPOINT_NUM=0,CPU_WIDTH=8,\
OUTPUT_DIR=$PWD/runs/output/spec17,GEM5_ROOT=$PWD \
  slurm/single_simpoint_job.slurm
```

### Monitor & collect
```bash
squeue -u $USER
# stats per run:
cat runs/output/<suite>/.../width8/<bench>/m5out/stats.txt
```

---

## 7. Practical notes & gotchas

- **Always run on compute nodes.** Booting the 16 GiB full-system image is
  multi-hour and must not run on the login node; submit via SLURM.
- **Index vs. suite.** `--benchmark-num` indexes the list selected by
  `GEM5_BENCH_SET`. Set the suite consistently across `ffcpt`/`ffrun` (the
  driver does this for you).
- **Atomic vs. O3 config.** Atomic CPUs have no O3 structures (`fuPool`, etc.),
  so detailed-core configuration is only applied when the run CPU is O3
  (`simrun`, or the O3 switch CPU in `ffrun`). `cpt`/`profile`/`simtake` skip it.
- **Checkpoint naming carries metadata.** SimPoint checkpoint names encode start
  instruction, weight, interval, and warmup, which `simrun` parses — don't
  rename them.
- **pyperformance is offline.** The image's `/home/gem5/pyperf` venv already
  contains all dependencies; no network is needed (or available) at run time.
