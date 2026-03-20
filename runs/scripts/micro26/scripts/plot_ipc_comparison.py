#!/usr/bin/env python3
"""
Grouped bar chart comparing IPC across approaches for each SPEC benchmark,
with the harmonic mean shown as the rightmost group.

Approaches
----------
  Baseline   : runs/output/micro26/baseline/12B_-1P
  Whisper    : runs/output/micro26/whisper/12B_-1P
  EDF-DMT/2  : runs/output/micro26/edf/dmt_slots/2
  N-Use/1    : runs/output/micro26/n-use/i-buffer-head/1

IPC per benchmark is computed as a weighted arithmetic mean over simpoints
(weights are embedded in the simpoint directory names and sum to 1).
The rightmost "HMean" bar shows the harmonic mean of per-benchmark IPCs.
"""

import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path("/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU")

APPROACHES: dict[str, Path] = {
    "Baseline":      ROOT / "runs/output/micro26/baseline/12B_-1P",
    "Whisper":       ROOT / "runs/output/micro26/whisper/12B_-1P",
    "Whisper-1B-2P": ROOT / "runs/output/micro26/whisper/1B_2P",
    "EDF-DMT/2":     ROOT / "runs/output/micro26/edf/dmt_slots/2",
    "N-Use/1":       ROOT / "runs/output/micro26/n-use/i-buffer-head/1",
}

OUTPUT_DIR = ROOT / "runs/output/micro26/graphs"

IPC_STAT = "system.cpu.ipc"

# ---------------------------------------------------------------------------
# Parsing helpers  (same conventions as the reference script)
# ---------------------------------------------------------------------------

def extract_weight(path: Path) -> float:
    """Return simpoint weight from directory name, defaulting to 1.0."""
    m = re.search(r'weight_([0-9]+\.[0-9]+)', str(path))
    return float(m.group(1)) if m else 1.0


def extract_benchmark(stats_file: Path) -> str:
    """
    Return the benchmark name from a stats.txt path.

    Expected layout:
        {base_dir}/width8/{benchmark}/{simpoint_dir}/m5out/stats.txt
    """
    return stats_file.parent.parent.parent.name


def extract_final_dump(content: str) -> str:
    """Return the last stats dump block found in *content*."""
    dumps = re.findall(
        r'---------- Begin Simulation Statistics ----------'
        r'(.*?)'
        r'---------- End Simulation Statistics   ----------',
        content, re.DOTALL
    )
    if len(dumps) >= 2:
        return dumps[-1]
    if len(dumps) == 1:
        return dumps[0]
    return ""


def parse_ipc(stats_file: Path):
    """Return the IPC value from the final dump of a stats.txt file."""
    try:
        with open(stats_file, 'r') as f:
            content = f.read()
    except OSError:
        return None

    dump = extract_final_dump(content)
    if not dump:
        return None

    for line in dump.splitlines():
        if not line.startswith(IPC_STAT):
            continue
        parts = line.split()
        if len(parts) >= 2:
            try:
                return float(parts[1])
            except ValueError:
                pass
    return None

# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_ipc(base_dir: Path) -> dict[str, float]:
    """
    Walk *base_dir* and return {benchmark: weighted_IPC}.

    Weighted IPC = sum(weight_i * ipc_i).  Since the simpoint weights for a
    benchmark sum to 1 this gives the correct representative IPC.
    Missing or unparseable simpoints are skipped with a warning.
    """
    stats_files = sorted(base_dir.glob("**/stats.txt"))
    if not stats_files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}

    weighted_ipc: dict[str, float] = defaultdict(float)
    weight_sum:   dict[str, float] = defaultdict(float)

    for sf in stats_files:
        ipc = parse_ipc(sf)
        if ipc is None:
            print(f"  WARNING: could not parse IPC from {sf}")
            continue
        benchmark = extract_benchmark(sf)
        weight    = extract_weight(sf)
        weighted_ipc[benchmark] += weight * ipc
        weight_sum[benchmark]   += weight

    # Normalise (guard against weights not summing exactly to 1).
    return {
        bm: weighted_ipc[bm] / weight_sum[bm]
        for bm in weighted_ipc
        if weight_sum[bm] > 0
    }


def harmonic_mean(values: list[float]) -> float:
    if not values:
        return float('nan')
    return len(values) / sum(1.0 / v for v in values if v > 0)

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot(
    approach_data: dict[str, dict[str, float]],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine the union of benchmarks present in *any* approach, sorted.
    all_benchmarks: list[str] = sorted(
        {bm for data in approach_data.values() for bm in data}
    )

    approach_names = list(approach_data.keys())
    n_approaches   = len(approach_names)
    n_benchmarks   = len(all_benchmarks)
    # x positions: one group per benchmark + one for "HMean"
    x_labels = all_benchmarks + ["HMean"]
    n_groups  = len(x_labels)

    # Build IPC matrix: shape (n_approaches, n_groups)
    ipc_matrix = np.full((n_approaches, n_groups), np.nan)
    for col, bm in enumerate(all_benchmarks):
        for row, name in enumerate(approach_names):
            ipc_matrix[row, col] = approach_data[name].get(bm, np.nan)

    # Harmonic mean column (last)
    for row, name in enumerate(approach_names):
        vals = [approach_data[name][bm]
                for bm in all_benchmarks
                if bm in approach_data[name]]
        ipc_matrix[row, -1] = harmonic_mean(vals)

    # ---- layout ----
    bar_width    = 0.7 / n_approaches
    group_center = np.arange(n_groups, dtype=float)
    offsets      = (np.arange(n_approaches) - (n_approaches - 1) / 2) * bar_width

    colors = plt.cm.tab10(np.linspace(0, 0.9, n_approaches))

    fig, ax = plt.subplots(figsize=(max(16, n_groups * 0.9), 6))

    for row, (name, color) in enumerate(zip(approach_names, colors)):
        heights = ipc_matrix[row]
        bars = ax.bar(
            group_center + offsets[row],
            heights,
            bar_width,
            label=name,
            color=color,
            zorder=2,
        )
        # Annotate each bar with its numeric value (skip NaN).
        for bar, h in zip(bars, heights):
            if np.isnan(h):
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h + 0.01,
                f"{h:.2f}",
                ha='center', va='bottom',
                fontsize=5, rotation=90,
            )

    # Separator before "HMean"
    ax.axvline(x=n_groups - 1.5, color='black', linewidth=1.0,
               linestyle='--', zorder=3)

    ax.set_xticks(group_center)
    ax.set_xticklabels(x_labels, rotation=45, ha='right', fontsize=8)
    ax.yaxis.grid(True, linestyle='--', alpha=0.4, zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylabel("IPC")
    ax.set_title("IPC Comparison Across Approaches (weighted simpoints)")
    ax.legend(title="Approach", bbox_to_anchor=(1.01, 1), loc='upper left',
              fontsize=8, title_fontsize=8, framealpha=0.9)

    plt.tight_layout()

    for fmt, subdir in [("png", "png"), ("pdf", "pdf")]:
        sub = output_dir / subdir
        sub.mkdir(parents=True, exist_ok=True)
        out_path = sub / "ipc_comparison.png" if fmt == "png" else sub / "ipc_comparison.pdf"
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        print(f"Saved {out_path}")

    plt.close(fig)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    approach_data: dict[str, dict[str, float]] = {}

    for name, base_dir in APPROACHES.items():
        if not base_dir.exists():
            print(f"SKIP {name}: directory not found ({base_dir})")
            continue
        print(f"Collecting IPC for {name} …")
        data = collect_ipc(base_dir)
        print(f"  → {len(data)} benchmarks found")
        approach_data[name] = data

    if not approach_data:
        print("No data found – nothing to plot.")
        return

    # Print per-benchmark summary.
    all_bms = sorted({bm for d in approach_data.values() for bm in d})
    header = f"{'Benchmark':<25}" + "".join(f"{n:>12}" for n in approach_data)
    print("\n" + header)
    print("-" * len(header))
    for bm in all_bms:
        row = f"{bm:<25}"
        for d in approach_data.values():
            v = d.get(bm, float('nan'))
            row += f"{v:>12.4f}"
        print(row)
    hmean_row = f"{'HMean':<25}"
    for d in approach_data.values():
        vals = [d[bm] for bm in all_bms if bm in d]
        hmean_row += f"{harmonic_mean(vals):>12.4f}"
    print("-" * len(header))
    print(hmean_row)

    plot(approach_data, OUTPUT_DIR)


if __name__ == "__main__":
    main()
