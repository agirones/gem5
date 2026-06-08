# gem5-NTNU: project structure and branch guide

Reference for how this repository is organised, which CPU implementation lives on
which git branch, and what kind of change belongs where.

For simulation mechanics (checkpoints, SimPoints, Apptainer, `invoke-run.py`),
see [SIMULATION_WORKFLOW.md](SIMULATION_WORKFLOW.md).

---

## 1. Branch hierarchy

**`infra`** is the shared platform branch. Implementation branches stack on top.

```
infra                           ← configs, SLURM, O3 evaluation platform, baseline + rebuttals
├── sereno                      ← + Sereno / whisper experiment scripts (params 1, 2)
│   ├── hybrid-wl               ← + squash-induced broadcast tracking (CPU + scripts)
│   ├── sereno-sqbcast          ← optional stats variant (analysis only)
│   └── sereno-stale            ← optional stats variant (analysis only)
├── explicit-data-forwarding    ← + DMT / explicit data forwarding (EDF)
└── n-use/OoO                   ← + N-Use table + I-Buffer (OoO promotion)
    └── n-use/InO               ← + FIFO I-Buffer promotion + head=12 scripts
```

**Rules**

- Cross-cutting changes → **`infra`**
- Sereno paper scripts / whisper analysis → **`sereno`** (on top of `infra`)
- Alternative CPU mechanisms → their branch, rebased on **`infra`**
- Hybrid-WL extends Sereno wakeup → rebase on **`sereno`**, not bare `infra`
- Never commit one implementation’s CPU changes on another implementation’s branch

---

## 2. Implementations at a glance

| Name | Branch | What differs | Typical `invoke-run` params |
|------|--------|--------------|-----------------------------|
| **Baseline** | `infra` (scripts) | Same binary as Sereno; full IQ broadcast | `broadcastMax=12`, `dependentsThreshold=-1` |
| **Sereno** | `sereno` (scripts) | Limited broadcast + precise wakeup (params only) | `broadcastMax=1`, `dependentsThreshold=2` |
| **Hybrid-WL** | `hybrid-wl` | Sereno threshold + squash-induced broadcast CPU | `broadcastMax=12`, `dependentsThreshold=2` |
| **EDF** | `explicit-data-forwarding` | DMT in IEW | `broadcastMax=12`, `dependentsThreshold=-1`, `numDmtSlots=2` |
| **N-Use (OoO)** | `n-use/OoO` | N-Use + I-Buffer; OoO promotion scan | `--n-slots=2`, `--i-buffer-size=32`, `--i-buffer-head=1` |
| **N-Use (InO)** | `n-use/InO` | FIFO I-Buffer promotion | same + `i-buffer-head=12` in dedicated scripts |

**Note on Baseline vs Sereno:** both use the **same gem5 binary** built from
`infra` (or any child branch). The O3 wakeup framework (`broadcastMax`,
`dependentsThreshold`, broadcast queue, precise wakeup) lives on **`infra`**
because Baseline experiments need it too. The `sereno` branch adds only the
**experiment scripts** that run the Sereno parameterisation.

Simulation **output** (`runs/output/`) is gitignored. Only **scripts** and
**source** are committed.

---

## 3. What belongs on `infra`

`infra` is the integration branch for everything shared across implementations.

### 3.1 CPU / O3 evaluation platform

Commit here:

- Parameterised broadcast wakeup: `broadcastMax`, `dependentsThreshold` in
  `src/cpu/o3/` (`iew.cc`, `iew.hh`, `inst_queue.cc`, `BaseO3CPU.py`)
- Evaluation statistics: `iqWakeupComparisons`,
  `nonReadySrcOpsDispatchedPerCycle`, `broadcastQueueOccupancyPerCycle`,
  register-pressure stats, etc.
- Compile-time limits for scaled cores (`MaxWidth`, `MaxDynInsts` in
  `src/cpu/o3/limits.hh`)

Do **not** commit on `infra`:

- DMT / EDF (`dmt`, `clearDMT`, `numDmtSlots`)
- Hybrid-wl squash-broadcast tracking
- N-Use / I-Buffer (`canFitNUse`, `promoteFromIBuffer`, …)

### 3.2 Configs and cluster infra

| Path | Purpose |
|------|---------|
| `configs/mast/profile-config-legacy.py` | gem5 full-system config |
| `configs/mast/invoke-run.py` | Apptainer front-end, simpoint loop, CLI |
| `configs/mast/benchmarks.py`, `spec17-benchmarks.txt`, `pyperf-benchmarks.txt` | Benchmark lists |
| `configs/mast/SIMULATION_WORKFLOW.md`, `PROJECT_BRANCHES.md` | Documentation |
| `slurm/single_simpoint_job.slurm`, `slurm/build_gem5.slurm` | Job launchers |
| `mast_gem5.def` | Apptainer definition |
| `.cursor/rules/gem5-commit-style.md` | Commit message conventions |

Shared CLI flags: `--core-scale`, `--l1-latency`, `--warmup-length`,
`--fast-forward-length`, `--measure-length`, `--broadcastMax`,
`--dependentsThreshold`, `ffrun` mode, etc.

N-Use flags (`--n-slots`, `--i-buffer-size`, `--i-buffer-head`) are added on
**`n-use/OoO`**.

### 3.3 Experiment scripts on `infra`

```
runs/scripts/micro26/
├── baseline/12B_-1P/          # Baseline (12, -1) runs + plots
├── scripts/                   # Shared IPC / comparison plot utilities
└── rebuttal/                  # Paper rebuttal sweeps
    ├── cache_lat/             # L1 latency; baseline vs sereno params
    ├── big_core/              # Core-scale 1.0x–4.0x
    ├── pyperf/                # pyperformance ffrun
    ├── warmup/                # Warmup 10M vs 50M + alt-impl orchestration
    └── ipc_relative/          # Multi-impl IPC comparison runners
```

Plot scripts should aggregate simpoint IPC as  
`sum(weight × simInsts) / sum(weight × numCycles)`.

---

## 4. What belongs on `sereno`

`sereno` = **`infra` + Sereno configuration scripts only** (typically one commit).

Commit here:

```
runs/scripts/micro26/
├── sereno/                    # ckpt, sqbcast, stale variants + sensibility sweeps
└── whisper/1B_2P/             # Canonical Sereno (1, 2) analysis plots
```

Do **not** commit on `sereno`:

- Shared infra, baseline scripts, or rebuttal orchestration (→ `infra`)
- Alternative implementation CPU or scripts (→ feature branches)
- `runs/scripts/micro26/hybrid-wl/` (→ `hybrid-wl`)

---

## 5. Feature branches

### 5.1 `explicit-data-forwarding` (EDF)

Rebase on **`infra`**. One CPU feature:

- DMT: `numDmtSlots`, `dmt[]`, `clearDMT`, `squashDMT`, dispatch stall
- Files: `src/cpu/o3/iew.{cc,hh}`, `inst_queue.{cc,hh}`, `BaseO3CPU.py`

Rebuttal runners on `infra` (checkout this branch to build/run):

- `rebuttal/warmup/edf/`, `rebuttal/ipc_relative/edf/`

### 5.2 `hybrid-wl`

Rebase on **`sereno`** (needs Sereno wakeup + scripts).

1. CPU: squash-induced broadcast tracking
2. Scripts: `runs/scripts/micro26/hybrid-wl/{ckpt,stale}/`

### 5.3 `n-use/OoO`

Rebase on **`infra`**. Shared N-Use base:

| Layer | Content |
|-------|---------|
| CPU | N-Use table + I-Buffer dispatch |
| Stats | N-Use / I-Buffer event statistics |
| Config | `--n-slots`, `--i-buffer-size`, `--i-buffer-head` |
| Infra | `slurm/multi_width_benchmark_*_jobs.slurm`, `sweep_*.sh` |
| Scripts | `runs/scripts/micro26/n-use/ooo-i-buffer/`, `ino-i-buffer/` trees |

**OoO promotion:** `promoteFromIBuffer` may promote any ready entry within the
head width (scan order).

### 5.4 `n-use/InO`

Rebase on **`n-use/OoO`**. Adds:

1. CPU: FIFO promotion (`break` at first non-ready I-Buffer entry)
2. Scripts: `ino-i-buffer/i-buffer-head/12/`

Canonical N-Use branch for rebuttals (`build_and_run_alt_implementations.sh`).

### 5.5 Optional Sereno analysis branches

Rebase on **`sereno`**:

| Branch | Extra content |
|--------|----------------|
| `sereno-sqbcast` | Unified broadcast stat naming |
| `sereno-stale` | Broadcast stat decomposition for stale analysis |

---

## 6. Rebuttal cross-implementation workflows

Scripts on **`infra`** check out implementation branches, rebuild, and submit:

| Key | Git branch |
|-----|------------|
| `edf` | `explicit-data-forwarding` |
| `hybrid-wl` | `hybrid-wl` |
| `n-use` | `n-use/InO` |

See `rebuttal/ipc_relative/IPC_RELATIVE.md`.

---

## 7. Repository layout

```
gem5-NTNU/
├── src/cpu/o3/              # O3 model (platform on infra; deltas per branch)
├── configs/mast/            # Configs + documentation
├── slurm/
├── runs/scripts/micro26/    # Committed scripts (split by branch — see above)
├── runs/output/             # gitignored simulation results
├── sweep_*.sh               # N-Use sweeps (n-use branches)
└── build/X86/gem5.opt       # built locally, not committed
```

---

## 8. Commit decision checklist

1. **Shared config, SLURM, baseline, rebuttal, or O3 evaluation stats?** → `infra`
2. **Sereno / whisper experiment scripts only?** → `sereno` (rebase on `infra` first)
3. **Alternative CPU mechanism?** → that branch, rebased on `infra`
4. **Hybrid-wl?** → `hybrid-wl`, rebased on `sereno`
5. **N-Use shared vs InO-only?** → `n-use/OoO` vs `n-use/InO`
6. **Simulation output / `__pycache__`?** → do not commit

Commit messages: gem5-style tags per `.cursor/rules/gem5-commit-style.md`.

---

## 9. Keeping branches in sync

```bash
git checkout infra && git pull   # platform first

git checkout sereno && git rebase infra
git checkout explicit-data-forwarding && git rebase infra
git checkout n-use/OoO && git rebase infra
git checkout n-use/InO && git rebase n-use/OoO
git checkout hybrid-wl && git rebase sereno
```

Publish (after rebase):

```bash
git push --force-with-lease origin infra
git push --force-with-lease origin sereno
git push --force-with-lease origin explicit-data-forwarding
git push --force-with-lease origin hybrid-wl
git push --force-with-lease origin n-use/OoO
git push --force-with-lease origin n-use/InO
```

**Remote note:** delete obsolete `origin/n-use` if `n-use/OoO` push fails with
`directory file conflict`.

---

## 10. Legacy branches

Not part of the current stack: `main`, `stable`, old `infra` at `087f9b0d8b`,
`wip-n-use`, `baseline_no_dest_no_wake_up`, etc. Use for archival reference only.
