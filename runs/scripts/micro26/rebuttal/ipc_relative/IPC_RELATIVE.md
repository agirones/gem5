# IPC-relative bar chart (rebuttal)

Grouped bar chart showing IPC change (%) of each non-baseline approach relative
to the baseline, matching `runs/scripts/micro26/scripts/plot_ipc_relative.py`.

**Rebuttal settings:** L1 latency = 4, warmup = 10M (from checkpoint names with
`warmup_10000000`).

## Data layout

All simulation output lives under `runs/output/micro26/rebuttal/cache_lat/`:

```
cache_lat/
  baseline/4/width8/{benchmark}/{simpoint}/m5out/stats.txt   (already collected)
  sereno/4/   ...                                            (already collected)
  hybrid-wl/4/...
  edf/4/...
  n-use/4/...
```

The plot script writes:

```
runs/output/micro26/rebuttal/ipc_relative/ipc_relative.tex
```

## Scripts

| Script | Git branch | Output |
|---|---|---|
| `hybrid-wl/run_experiment.sh` | `hybrid-wl` | `cache_lat/hybrid-wl/4/` |
| `edf/run_experiment.sh` | `explicit-data-forwarding` | `cache_lat/edf/4/` |
| `n-use/run_experiment.sh` | `n-use/InO` | `cache_lat/n-use/4/` |
| `plot_ipc_relative.py` | any | `ipc_relative.tex` |

## Configuration per approach

| Approach | Parameters |
|---|---|
| Baseline | `broadcastMax=12`, `dependentsThreshold=-1` |
| Sereno | `broadcastMax=1`, `dependentsThreshold=2` |
| Hybrid-WL | `broadcastMax=12`, `dependentsThreshold=2` |
| EDF | `broadcastMax=12`, `dependentsThreshold=-1`, `numDmtSlots=2` (branch default) |
| N-Use | `n-slots=2`, `i-buffer-head=2` (matches `micro26/n-use/ino-i-buffer/i-buffer-head/2`) |

All approaches share `L1_LATENCY=4` and `WARMUP_LENGTH=-1` (read 10M warmup
from the checkpoint name).

## Workflow

For each approach, checkout the branch, build gem5, then submit simpoint jobs.

### Hybrid-WL

```bash
git checkout hybrid-wl
sbatch slurm/build_gem5.slurm /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU
# wait for build to finish, then:
./runs/scripts/micro26/rebuttal/ipc_relative/hybrid-wl/run_experiment.sh
```

Uses the stock `slurm/single_simpoint_job.slurm` (forwards `L1_LATENCY` and
`WARMUP_LENGTH` to `invoke-run.py`).

### EDF

```bash
git checkout explicit-data-forwarding
sbatch slurm/build_gem5.slurm /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU
./runs/scripts/micro26/rebuttal/ipc_relative/edf/run_experiment.sh
```

Also uses the stock `slurm/single_simpoint_job.slurm`.

### N-Use

```bash
git checkout n-use/InO
sbatch slurm/build_gem5.slurm /cluster/home/andreug/research/EECS-NTNU/gem5-NTNU
./runs/scripts/micro26/rebuttal/ipc_relative/n-use/run_experiment.sh
```

N-Use uses a dedicated SLURM script (`n-use/single_simpoint_job.slurm`) because
the stock `slurm/single_simpoint_job.slurm` on `n-use/InO` does not forward
`--i-buffer-head` / `--n-slots` to `invoke-run.py`.

### Generate the graph

Once all runs finish:

```bash
python3 runs/scripts/micro26/rebuttal/ipc_relative/plot_ipc_relative.py
```

Import the output in Overleaf with `\input{ipc_relative.tex}` inside a
`standalone`-compatible document.

## IPC computation

Per-benchmark IPC is a weighted sum over simpoints:

```
IPC = sum(weight * simInsts) / sum(weight * numCycles)
```

Weights are embedded in simpoint directory names and sum to 1. The rightmost bar
group shows harmonic-mean EWS (Eeckhout 2024):

```
EWS = ((HM_optimized / HM_baseline) - 1) * 100
```
