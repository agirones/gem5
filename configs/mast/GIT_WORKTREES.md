# Git Worktrees for Parallel gem5 Implementations

This document describes how to run multiple gem5 CPU implementations in parallel
using **git worktrees**, while keeping all simulation output in a single global
directory.

For branch roles and what belongs on each branch, see
[PROJECT_BRANCHES.md](PROJECT_BRANCHES.md). For checkpoint and SimPoint mechanics,
see [SIMULATION_WORKFLOW.md](SIMULATION_WORKFLOW.md).

---

## 1. Goals

| Problem | Worktree solution |
|---|---|
| `git checkout` between implementations invalidates `build/` | Each worktree has its own `build/X86/gem5.opt` |
| Only one branch can be checked out in a single tree | One worktree per implementation branch |
| Simulation data scattered across checkouts | All trees share one output store via symlink |
| Rebuttal scripts that `git checkout` + build sequentially | Build and run from the matching worktree instead |

**Worktrees isolate git state and binaries.** Parallel experiments on the *same*
implementation are handled by SLURM and distinct output paths — not by creating
more worktrees for each experiment.

---

## 2. Directory layout

All gem5 checkouts are **siblings** under `EECS-NTNU/`. Simulation data lives
**outside** git, in a shared `output/` directory reached through a relative
symlink in every checkout.

```
/cluster/home/andreug/research/EECS-NTNU/
│
├── output/                          ← global simulation data (not in git)
│   ├── micro26/
│   ├── build_gem5/
│   └── ...
│
├── gem5-NTNU/                       ← main worktree  [infra]
│   ├── .git
│   ├── build/X86/gem5.opt           ← per-worktree binary
│   └── runs/
│       ├── scripts/                 ← tracked by git
│       └── output → ../../output       ← symlink (not tracked)
│
├── gem5-NTNU-baseline/              ← worktree  [baseline]
│   └── runs/output → ../../output
│
├── gem5-NTNU-sereno/                ← worktree  [sereno]
│   └── runs/output → ../../output
│
├── gem5-NTNU-explicit-data-forwarding/  ← worktree  [explicit-data-forwarding]
│   └── runs/output → ../../output
│
├── gem5-NTNU-hybrid-wl/             ← worktree  [hybrid-wl]
│   └── runs/output → ../../output
│
├── gem5-NTNU-n-use-OoO/             ← worktree  [n-use/OoO]
│   └── runs/output → ../../output
│
└── gem5-NTNU-n-use-InO/             ← worktree  [n-use/InO]
    └── runs/output → ../../output
```

### What lives where

| Path | Git-tracked? | Shared across worktrees? |
|---|---|---|
| `src/`, `configs/`, `slurm/` | Yes (per branch) | No — each worktree has its branch's tree |
| `runs/scripts/` | Yes | No — scripts differ by branch (see PROJECT_BRANCHES.md) |
| `build/` | No (gitignored) | No — one binary per worktree |
| `runs/output` | No (under `runs/**` ignore) | Yes — symlink to `../../output` |
| `../../output/` | No | Yes — single global store (~134 GB) |

---

## 3. Branch → worktree mapping

| Implementation | Git branch | Worktree directory |
|---|---|---|
| Baseline / shared infra | `infra` | `gem5-NTNU` (main) |
| Baseline (parallel runs) | `baseline` | `gem5-NTNU-baseline` |
| Sereno | `sereno` | `gem5-NTNU-sereno` |
| EDF | `explicit-data-forwarding` | `gem5-NTNU-explicit-data-forwarding` |
| Hybrid-WL | `hybrid-wl` | `gem5-NTNU-hybrid-wl` |
| N-Use (OoO) | `n-use/OoO` | `gem5-NTNU-n-use-OoO` |
| N-Use (InO) | `n-use/InO` | `gem5-NTNU-n-use-InO` |

Optional analysis branches (`sereno-sqbcast`, `sereno-stale`) only need a
worktree while actively in use.

### Baseline parallel worktree (`baseline` branch)

Baseline and Sereno share the **same gem5 binary** (see PROJECT_BRANCHES.md);
only run parameters differ (`broadcastMax=12`, `dependentsThreshold=-1` vs
`1`/`2`). Git allows only one checkout per branch, so a second worktree for
baseline runs uses a **`baseline` branch** pointing at the same commit as
`sereno`:

```bash
git branch baseline sereno
./configs/mast/setup-worktree.sh add baseline
```

`gem5-NTNU-baseline` and `gem5-NTNU-sereno` then have identical trees but
separate `build/` directories and can run SLURM jobs in parallel. After
rebasing `sereno`, fast-forward the alias:

```bash
git branch -f baseline sereno
cd ../gem5-NTNU-baseline && git reset --hard baseline
```

Baseline **scripts** still live on `infra`; use `GEM5_ROOT` pointing at
`gem5-NTNU-baseline` when submitting baseline-parameter jobs.

**Git rule:** each branch can be checked out in **at most one** worktree at a
time. You cannot have two worktrees both on `explicit-data-forwarding`.

---

## 4. The `runs/output` symlink

### Why a symlink

Experiment scripts and configs refer to output as `${GEM5_ROOT}/runs/output/...`.
A symlink in every worktree preserves those paths while writing to the global
store at `/cluster/home/andreug/research/EECS-NTNU/output`.

From any sibling worktree, create the symlink **from the worktree root** with a
target relative to `runs/`:

```
runs/output  →  ../../output
```

(`../../output` is resolved from `runs/`, not from the repo root: up to the
worktree, up to `EECS-NTNU/`, then into `output/`.)

This survives machine moves as long as the sibling layout is preserved.

### Why not commit the symlink

Root `.gitignore` ignores all of `runs/` except scripts:

```
runs/**
!runs/**/scripts/
!runs/**/scripts/**
```

`runs/output` is intentionally excluded. The symlink is **environment setup**,
like `build/` or `mast_gem5.sif` — it depends on your cluster layout, not on
CPU implementation code. Keeping it out of git means:

- No `.gitignore` exceptions to maintain
- No merge/rebase conflicts on a path every branch would need
- New worktrees get a predictable bootstrap step instead of silent inconsistency

### Manual creation

From any worktree root:

```bash
mkdir -p runs
ln -sfn ../../output runs/output
```

Verify:

```bash
readlink runs/output          # → ../../output
readlink -f runs/output       # → /cluster/home/andreug/research/EECS-NTNU/output
ls runs/output/micro26        # existing data should be visible
```

---

## 5. Automated setup (`setup-worktree.sh`)

A tracked helper script lives at `configs/mast/setup-worktree.sh`. It handles
symlink creation and optional worktree provisioning.

Make it executable once:

```bash
chmod +x configs/mast/setup-worktree.sh
```

### 5.1 Link only (main or existing worktree)

```bash
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU
./configs/mast/setup-worktree.sh link
```

Creates or refreshes `runs/output → ../../output` and prints the resolved path.

### 5.2 Verify

```bash
./configs/mast/setup-worktree.sh verify
```

Exits non-zero if the symlink is missing or points elsewhere.

### 5.3 Add a new worktree (link included)

```bash
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU

./configs/mast/setup-worktree.sh add explicit-data-forwarding
# → creates ../gem5-NTNU-edf

./configs/mast/setup-worktree.sh add n-use/InO
# → creates ../gem5-NTNU-n-use-InO

./configs/mast/setup-worktree.sh add sereno /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU-sereno
# → explicit path override
```

`add` runs `git worktree add`, then calls `link` in the new tree.

### 5.4 Bootstrap all implementation worktrees

```bash
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU
./configs/mast/setup-worktree.sh bootstrap
```

`bootstrap` links the main checkout, then adds any missing worktrees for the
standard implementation branches (`sereno`, `explicit-data-forwarding`,
`hybrid-wl`, `n-use/OoO`, `n-use/InO`). Existing paths are skipped but get a
fresh symlink.

### 5.5 Refresh symlinks in every worktree

```bash
./configs/mast/setup-worktree.sh link-all
```

The main tree (`gem5-NTNU`) should stay on `infra`. If it is on another branch,
move that branch to its own worktree first:

```bash
git checkout infra
./configs/mast/setup-worktree.sh add n-use/InO
```

---

## 6. Building gem5

Each worktree compiles its own binary. Builds are **not** shared.

```bash
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU-edf
sbatch slurm/build_gem5.slurm "$(pwd)"
```

Or interactively inside Apptainer:

```bash
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU-edf
apptainer exec -B /cluster:/cluster mast_gem5.sif \
    scons -j "$(nproc)" build/X86/gem5.opt --ignore-style
```

Build logs go to `runs/output/build_gem5/slurm_logs/` (the shared global store).
When building several implementations in parallel, submit one build job per
worktree with that worktree's path as the argument.

---

## 7. Running simulations

### Set `GEM5_ROOT` to the active worktree

Most experiment scripts accept an optional `GEM5_ROOT` argument defaulting to the
main repo:

```bash
GEM5_ROOT=/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU-edf \
    runs/scripts/micro26/rebuttal/warmup/edf/run_experiment.sh
```

SLURM submission from a script:

```bash
export GEM5_ROOT=/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU-edf
./runs/scripts/micro26/rebuttal/warmup/edf/run_experiment.sh "${GEM5_ROOT}"
```

### Parallel experiments, same implementation

From **one** worktree, submit many jobs with different output paths. Scripts
already isolate results, for example:

- `runs/output/micro26/rebuttal/cache_lat/edf/4/`
- `runs/output/micro26/rebuttal/warmup/edf/50M/`

No extra worktrees are needed.

### Parallel different implementations

Use a different worktree (and `GEM5_ROOT`) per implementation. Example: run
cache-latency EDF jobs from `gem5-NTNU-edf` and Sereno jobs from
`gem5-NTNU-sereno` at the same time.

### Output path defaults in `invoke-run.py`

`configs/mast/invoke-run.py` hardcodes a default `--output-dir` pointing at the
main repo. When running from another worktree, pass:

```bash
--output-dir "${GEM5_ROOT}/runs/output"
```

`profile-config-legacy.py` resolves `runs/output` relative to the config file's
repo root, so it follows the active worktree automatically.

---

## 8. Replacing branch-checkout orchestration

`runs/scripts/micro26/rebuttal/warmup/build_and_run_alt_implementations.sh`
checks out each implementation branch sequentially, rebuilds, and runs. With
worktrees, run the per-implementation `run_experiment.sh` directly from the
matching tree instead:

| Key | Branch | Worktree | Script |
|---|---|---|---|
| `edf` | `explicit-data-forwarding` | `gem5-NTNU-explicit-data-forwarding` | `rebuttal/warmup/edf/run_experiment.sh` |
| `hybrid-wl` | `hybrid-wl` | `gem5-NTNU-hybrid-wl` | `rebuttal/warmup/hybrid-wl/run_experiment.sh` |
| `n-use` | `n-use/InO` | `gem5-NTNU-n-use-InO` | `rebuttal/warmup/n-use/run_experiment.sh` |

Build all three in parallel (three `sbatch` calls, three paths), then submit
experiment jobs from each worktree. Set `SKIP_BUILD=1` in the legacy orchestrator
if you still use it but builds were done via worktrees.

---

## 9. Adding a new implementation branch

1. Create and rebase the branch on the correct parent (`infra` or `sereno`) —
   see [PROJECT_BRANCHES.md](PROJECT_BRANCHES.md) §8–9.
2. Add a worktree and symlink:

   ```bash
   ./configs/mast/setup-worktree.sh add my-new-branch
   ```

3. Build in the new tree.
4. Run a single simpoint smoke test; confirm output appears under
   `runs/output/...` and resolves to the global store.
5. Commit CPU changes on the feature branch; commit shared scripts on `infra`.

---

## 10. Keeping worktrees up to date

Rebase branches in dependency order (infra first, then children). In each
worktree, pull the rebased branch without checking out elsewhere:

```bash
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU-edf
git fetch origin
git rebase origin/infra        # or: git merge, per your workflow
```

Rebuild after CPU or build-system changes. Scripts-only updates on `infra` may
not require a rebuild in implementation worktrees unless you need those scripts
locally (consider merging/rebasing `infra` into the feature branch).

Refresh the symlink after any manual `runs/` cleanup:

```bash
./configs/mast/setup-worktree.sh link
```

---

## 11. Removing a worktree

```bash
cd /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU
git worktree remove /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU-edf
git worktree prune
```

This removes the checkout and its local `build/`. It does **not** delete
`output/` — global simulation data is preserved.

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `runs/output/micro26` empty or missing | Symlink not created | `./configs/mast/setup-worktree.sh link` |
| `readlink -f runs/output` wrong path | Broken or absolute symlink | `ln -sfn ../../output runs/output` |
| `fatal: 'branch' is already checked out` | Branch in another worktree | Use that worktree, or remove the other one |
| Jobs write to main repo path | Wrong `GEM5_ROOT` | Export or pass the worktree path |
| `invoke-run` writes outside worktree | Hardcoded `--output-dir` default | Pass `--output-dir "${GEM5_ROOT}/runs/output"` |
| Build succeeds but sim fails | Stale binary after rebase | Rebuild in that worktree |

---

## 13. Quick reference

```bash
# Symlink in current checkout
./configs/mast/setup-worktree.sh link

# Main + all standard implementation worktrees
./configs/mast/setup-worktree.sh bootstrap

# Add worktree + symlink
./configs/mast/setup-worktree.sh add explicit-data-forwarding

# List worktrees
git worktree list

# Build in a worktree
cd ../gem5-NTNU-edf && sbatch slurm/build_gem5.slurm "$(pwd)"

# Run experiment
GEM5_ROOT=/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU-edf \
    runs/scripts/micro26/rebuttal/warmup/edf/run_experiment.sh

# Verify symlink
./configs/mast/setup-worktree.sh verify
```
