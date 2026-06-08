# gem5-NTNU: project structure and branch guide

Reference for how this repository is organised, which CPU implementation lives on
which git branch, and what kind of change belongs where.

For simulation mechanics (checkpoints, SimPoints, Apptainer, `invoke-run.py`),
see [SIMULATION_WORKFLOW.md](SIMULATION_WORKFLOW.md).

---

## 1. Branch hierarchy

All active implementation branches are rebased on top of **`sereno`**. Each
feature branch should contain **only** the CPU mechanism (and its own experiment
scripts) on top of the shared Sereno baseline.

```
sereno                          ← shared baseline (paper + infra + rebuttals)
├── explicit-data-forwarding    ← + DMT / explicit data forwarding (EDF)
├── hybrid-wl                   ← + hybrid-wl wakeup (squash-induced broadcast)
├── n-use/OoO                   ← + N-Use table + I-Buffer (out-of-order promotion)
│   └── n-use/InO               ← + in-order FIFO I-Buffer promotion + head=12 scripts
├── sereno-sqbcast              ← optional Sereno stats variant (analysis only)
└── sereno-stale                ← optional Sereno stats variant (analysis only)
```

**Rule:** never commit one implementation’s CPU changes on another
implementation’s branch. Cross-cutting infra and Sereno-paper scripts go on
`sereno`; comparison/rebuttal scripts that *run* multiple implementations may
live on `sereno` as long as they only reference branches by checkout (they do
not embed implementation-specific CPU code).

---

## 2. Implementations at a glance

| Name | Branch | Wakeup / dispatch idea | Typical `invoke-run` params |
|------|--------|------------------------|-----------------------------|
| **Baseline** | `sereno` (scripts only) | Full IQ broadcast (`broadcastMax=12`, no precise threshold) | `broadcastMax=12`, `dependentsThreshold=-1` |
| **Sereno** | `sereno` | Limited broadcast + precise wakeup by dependent count | `broadcastMax=1`, `dependentsThreshold=2` |
| **Hybrid-WL** | `hybrid-wl` | Baseline broadcast width + Sereno-style threshold + **squash-induced broadcast tracking** | `broadcastMax=12`, `dependentsThreshold=2` |
| **EDF** | `explicit-data-forwarding` | **Dynamic Mapping Table (DMT)** in IEW; targeted dispatch stall / explicit wakeup | `broadcastMax=12`, `dependentsThreshold=-1`, `numDmtSlots=2` |
| **N-Use (OoO)** | `n-use/OoO` | **N-Use table** + **I-Buffer** at dispatch; promotes ready entries from I-Buffer in scan order | `--n-slots=2`, `--i-buffer-size=32`, `--i-buffer-head=1` (sweeps vary) |
| **N-Use (InO)** | `n-use/InO` | Same as OoO, but I-Buffer promotion is **strict FIFO** (stops at first non-ready entry) | same + `i-buffer-head=12` in dedicated scripts |

Simulation **output** (`runs/output/`) is gitignored. Only **scripts** and
**source** are committed.

---

## 3. What belongs on `sereno`

`sereno` is the integration branch for the MICRO'26 Sereno work and everything
that is shared across implementations.

### 3.1 CPU / O3 model (Sereno mechanism)

Commit here:

- `broadcastMax`, `dependentsThreshold` parameters and wakeup logic in
  `src/cpu/o3/` (`iew.cc`, `iew.hh`, `inst_queue.cc`, …)
- Sereno statistics: `iqWakeupComparisons`, `nonReadySrcOpsDispatchedPerCycle`,
  `broadcastQueueOccupancyPerCycle`, register-pressure stats at dispatch, etc.
- Compile-time limits for scaled cores (`MaxWidth`, `MaxDynInsts` in
  `src/cpu/o3/limits.hh`) when needed for rebuttal sweeps

Do **not** commit on `sereno`:

- DMT / EDF tables (`dmt`, `clearDMT`, `numDmtSlots`)
- Hybrid-wl squash-broadcast tracking (beyond what Sereno already has)
- N-Use / I-Buffer dispatch paths (`canFitNUse`, `promoteFromIBuffer`, …)

### 3.2 Configs and cluster infra

Commit here:

| Path | Purpose |
|------|---------|
| `configs/mast/profile-config-legacy.py` | gem5 full-system config (O3 CPU, caches, modes) |
| `configs/mast/invoke-run.py` | Front-end: Apptainer, simpoint loop, CLI args |
| `configs/mast/benchmarks.py`, `spec17-benchmarks.txt`, `pyperf-benchmarks.txt` | Benchmark lists |
| `configs/mast/SIMULATION_WORKFLOW.md` | How to run SPEC / pyperformance flows |
| `slurm/single_simpoint_job.slurm`, `slurm/build_gem5.slurm` | Job launchers |
| `mast_gem5.def` | Apptainer definition |
| `.cursor/rules/gem5-commit-style.md` | Commit message conventions for agents |

Shared CLI flags on `sereno` include: `--core-scale`, `--l1-latency`,
`--warmup-length`, `--fast-forward-length`, `--measure-length`, `ffrun` mode,
etc.

N-Use-specific flags (`--n-slots`, `--i-buffer-size`, `--i-buffer-head`) are
added on **`n-use/OoO`** (and inherited by `n-use/InO`), not on bare `sereno`.

### 3.3 Experiment scripts (`runs/scripts/micro26/`)

Commit on `sereno`:

```
runs/scripts/micro26/
├── baseline/12B_-1P/          # Baseline (12, -1) runs + plots
├── sereno/                    # Sereno variants (ckpt, sqbcast, stale, …)
├── whisper/1B_2P/             # Canonical Sereno (1, 2) analysis plots
├── scripts/                   # Shared IPC / comparison plot utilities
└── rebuttal/                  # Paper rebuttal sweeps (see §5)
    ├── cache_lat/             # L1 latency 2–4, baseline vs sereno
    ├── big_core/              # Core-scale 1.0x–4.0x
    ├── pyperf/                # Python / pyperformance ffrun
    ├── warmup/                # Warmup 10M vs 50M (sereno + baseline;
    │                          #   alt-impl runners live in subdirs)
    └── ipc_relative/          # Multi-impl IPC comparison (scripts only;
                               #   each impl checked out separately to run)
```

Plot scripts should aggregate simpoint IPC as  
`sum(weight × simInsts) / sum(weight × numCycles)` (not a weighted mean of
`system.cpu.ipc`).

### 3.4 Sereno analysis branches (optional)

These are **thin** branches for extra statistics / naming experiments. They
should stay rebased on `sereno`.

| Branch | Extra content |
|--------|----------------|
| `sereno-sqbcast` | Unified broadcast stat naming (`broadcastNecessary`, etc.) |
| `sereno-stale` | Broadcast stat decomposition for stale / mispred analysis |

Use these when iterating on **stats only** for Sereno variants (`sereno/stale/`,
`sereno/sqbcast/` scripts on `sereno`).

---

## 4. Feature branches — what to commit

### 4.1 `explicit-data-forwarding` (EDF)

**One logical feature** on top of `sereno`:

- DMT in IEW: `numDmtSlots`, `dmt[]`, `clearDMT`, `squashDMT`, dispatch stall
  when DMT slots are full
- Files: `src/cpu/o3/iew.{cc,hh}`, `inst_queue.{cc,hh}`, `BaseO3CPU.py`

**Do not commit here:** Sereno-only script additions, N-Use, hybrid-wl, or
rebuttal sweeps (those go on `sereno` or the relevant branch).

Rebuttal runners that *use* EDF (checkout this branch, then submit jobs) live on
`sereno`:

- `runs/scripts/micro26/rebuttal/warmup/edf/`
- `runs/scripts/micro26/rebuttal/ipc_relative/edf/`

### 4.2 `hybrid-wl`

**Two commits** typical on top of `sereno`:

1. CPU: hybrid-wl wakeup with squash-induced broadcast tracking  
   (`src/cpu/o3/iew.{cc,hh}`, `inst_queue.{cc,hh}`)
2. Scripts: `runs/scripts/micro26/hybrid-wl/{ckpt,stale}/` (and rebuttal runners
   under `rebuttal/warmup/hybrid-wl/`, `rebuttal/ipc_relative/hybrid-wl/`)

Params: `broadcastMax=12`, `dependentsThreshold=2`.

### 4.3 `n-use/OoO`

**Shared N-Use base** (5 commits on top of `sereno`):

| Layer | Content |
|-------|---------|
| CPU | N-Use table + I-Buffer at dispatch (`canFitNUse`, `insertNUse`, `promoteFromIBuffer`, …) |
| Stats | N-Use / I-Buffer event statistics |
| Config | `--n-slots`, `--i-buffer-size`, `--i-buffer-head` in `invoke-run.py` / `profile-config-legacy.py` |
| Infra | `slurm/multi_width_benchmark_*_jobs.slurm`, `sweep_*.sh` |
| Scripts | `runs/scripts/micro26/n-use/ooo-i-buffer/` and `ino-i-buffer/` layout (both variants’ script trees may exist for organisation; **OoO promotion behaviour** is the default scan in `promoteFromIBuffer`) |

**Promotion policy (OoO):** `promoteFromIBuffer` scans the deque and may promote
any ready instruction within the head width (younger entries can pass older
non-ready ones).

### 4.4 `n-use/InO`

**Extends `n-use/OoO`** with 2 additional commits:

1. **CPU:** in-order FIFO promotion — `break` at first non-ready I-Buffer entry
2. **Scripts:** `runs/scripts/micro26/n-use/ino-i-buffer/i-buffer-head/12/`

Rebuttal workflows use **`n-use/InO`** as the canonical N-Use branch (see
`build_and_run_alt_implementations.sh`).

**Do not duplicate** the five shared N-Use commits on both `n-use/OoO` and
`n-use/InO` with different hashes. Preferred workflow:

```bash
git checkout n-use/OoO
# … commit shared N-Use changes …
git checkout n-use/InO
git rebase n-use/OoO
# … commit only InO-specific changes …
```

---

## 5. Rebuttal cross-implementation workflows

Some rebuttal scripts on `sereno` orchestrate **multiple branches** by checking
out each branch, rebuilding gem5, and submitting jobs.

Example: `runs/scripts/micro26/rebuttal/warmup/build_and_run_alt_implementations.sh`

| Key | Git branch |
|-----|------------|
| `edf` | `explicit-data-forwarding` |
| `hybrid-wl` | `hybrid-wl` |
| `n-use` | `n-use/InO` |

Document new comparison studies in a small `*.md` next to the scripts (as in
`rebuttal/ipc_relative/IPC_RELATIVE.md`).

---

## 6. Repository layout (top level)

```
gem5-NTNU/
├── src/cpu/o3/              # O3 CPU model (implementation-specific per branch)
├── configs/mast/            # Simulation configs + this guide + SIMULATION_WORKFLOW.md
├── slurm/                   # SLURM job templates
├── runs/
│   ├── scripts/micro26/     # Committed experiment + plot scripts
│   ├── output/              # Simulation results (gitignored)
│   ├── disk-images/         # Local disk images (mostly gitignored)
│   └── legacy-checkpoints/  # Post-boot checkpoints (gitignored)
├── sweep_*.sh               # N-Use parameter sweep wrappers (on n-use branches)
├── mast_gem5.def            # Apptainer image definition
└── build/X86/gem5.opt       # Built binary (not committed)
```

### Output directory convention

```
runs/output/micro26/
├── baseline/12B_-1P/width8/{benchmark}/{simpoint}/m5out/stats.txt
├── sereno/ckpt/width8/...
├── hybrid-wl/...
├── n-use/...
└── rebuttal/
    ├── cache_lat/{baseline,sereno}/{2,3,4}/...
    ├── big_core/{baseline,sereno}/{1.0x,…,4.0x}/...
    ├── warmup/{baseline,sereno,edf,hybrid-wl,n-use}/{10M,50M}/...
    └── pyperf/{baseline,sereno}/width8/{benchmark}/m5out/stats.txt
```

---

## 7. Commit decision checklist

When staging a change, ask:

1. **Does it modify CPU wakeup/dispatch for a specific alternative design?**  
   → Commit on that feature branch only (`explicit-data-forwarding`, `hybrid-wl`,
   `n-use/OoO`, or `n-use/InO`).

2. **Is it shared infra, Sereno CPU, or a rebuttal script for baseline+sereno?**  
   → Commit on `sereno`.

3. **Is it an N-Use script/flag used by both OoO and InO?**  
   → Commit on `n-use/OoO`, then rebase `n-use/InO`.

4. **Is it InO-only FIFO behaviour or head=12 scripts?**  
   → Commit on `n-use/InO` only.

5. **Is it simulation output, build artefacts, or `__pycache__`?**  
   → Do not commit.

6. **Is it a Sereno stats naming experiment?**  
   → Consider `sereno-sqbcast` or `sereno-stale`.

### Commit messages

Follow gem5-style tags (`cpu-o3`, `configs`, `scripts`, `infra`, …). See
`.cursor/rules/gem5-commit-style.md`. Do not add `Co-authored-by` trailers.

---

## 8. Keeping branches in sync

After new commits on `sereno`, rebase feature branches:

```bash
git checkout sereno && git pull   # or push first if you are ahead

git checkout explicit-data-forwarding && git rebase sereno
git checkout hybrid-wl             && git rebase sereno
git checkout n-use/OoO             && git rebase sereno
git checkout n-use/InO             && git rebase n-use/OoO
```

Resolve conflicts by **keeping sereno’s Sereno wakeup code** and **re-applying**
the branch-specific mechanism (DMT, hybrid-wl, or N-Use/I-Buffer).

Publish with lease (after rebase):

```bash
git push --force-with-lease origin sereno
git push --force-with-lease origin explicit-data-forwarding
git push --force-with-lease origin hybrid-wl
git push --force-with-lease origin n-use/OoO
git push --force-with-lease origin n-use/InO
```

**Remote note:** branch names `n-use/OoO` and `n-use/InO` cannot coexist with a
branch literally named `n-use`. Delete obsolete `origin/n-use` if push is
rejected with `directory file conflict`.

---

## 9. Legacy / inactive branches

These exist in the repo history but are **not** part of the current MICRO'26
implementation stack:

`main`, `stable`, `baseline_no_dest_no_wake_up`, `japanese_proposal`,
`wip-n-use`, `wip-ideal_mem_spec`, `fast_mem`, `iohole`, etc.

Use them only for archival comparison; new work should target the branches in
§1.

---

## 10. Quick reference — files touched per implementation

| Implementation | Primary source files |
|----------------|---------------------|
| Sereno (all branches) | `src/cpu/o3/iew.{cc,hh}`, `inst_queue.{cc,hh}`, `BaseO3CPU.py` |
| EDF | above + DMT types/methods in `iew`, `clearDMT` calls in `inst_queue` |
| Hybrid-WL | above + squash-broadcast queue logic in `iew` / `inst_queue` |
| N-Use | above + `dyn_inst.hh` (in-NUse/in-IBuffer flags), I-Buffer deque in `inst_queue` |

Config wiring for an implementation’s parameters belongs in the same branch as
the CPU change, except shared rebuttal runners on `sereno` which only pass flags
via environment variables / `invoke-run.py` CLI.
