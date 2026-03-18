#!/usr/bin/env python3
"""
Plot a stacked relative bar chart of broadcastQueueOccupancyPerCycle
for each benchmark under runs/output/micro26/whisper/1B_2P.

Each bar shows the fraction of cycles spent at each occupancy level (0, 1, 2, …).
The weighted average occupancy is printed next to each bar.
An extra "Average" bar at the right shows the cross-benchmark mean.
"""

import glob
import os
import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(
    "/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/"
    "runs/output/micro26/whisper/1B_2P/width8"
)
OUTPUT_DIR = Path(
    "/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/"
    "runs/output/micro26/whisper/1B_2P/graphs"
)
STAT_PREFIX = "system.cpu.iew.broadcastQueueOccupancyPerCycle"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_weight(path: Path) -> float:
    """Return simpoint weight from directory name, defaulting to 1.0."""
    m = re.search(r'weight_([0-9]+\.[0-9]+)', str(path))
    return float(m.group(1)) if m else 1.0


def extract_benchmark(path: Path) -> str:
    """Return the benchmark name (e.g. '600.perlbench_s') from the path."""
    # Expected layout: BASE_DIR / {benchmark} / {simpoint_dir} / m5out / stats.txt
    return path.parent.parent.parent.name


def extract_final_dump(content: str) -> str:
    """Return the last stats dump found in the file content."""
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


def parse_histogram(stats_file: Path) -> dict[int, float]:
    """
    Parse the broadcastQueueOccupancyPerCycle histogram from a stats.txt.
    Returns a dict mapping occupancy level -> raw count.
    """
    with open(stats_file, 'r') as f:
        content = f.read()

    dump = extract_final_dump(content)
    if not dump:
        return {}

    counts: dict[int, float] = {}
    for line in dump.splitlines():
        if not line.startswith(STAT_PREFIX + "::"):
            continue
        # e.g.  system.cpu.iew.broadcastQueueOccupancyPerCycle::3   42   ...
        suffix = line[len(STAT_PREFIX) + 2:].split()[0]
        try:
            level = int(suffix)
        except ValueError:
            continue  # skip 'mean', 'stdev', 'samples', etc.
        try:
            value = int(line.split()[1])
        except (IndexError, ValueError):
            continue
        counts[level] = value
    return counts

# ---------------------------------------------------------------------------
# Collect data
# ---------------------------------------------------------------------------

def collect_benchmark_histograms(base_dir: Path) -> dict[str, dict[int, float]]:
    """
    For each benchmark aggregate the weighted histogram across all simpoints.
    Returns {benchmark: {level: weighted_count}}.
    """
    stats_files = sorted(base_dir.glob("**/stats.txt"))
    benchmark_data: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))

    for sf in stats_files:
        benchmark = extract_benchmark(sf)
        weight = extract_weight(sf)
        counts = parse_histogram(sf)
        for level, count in counts.items():
            benchmark_data[benchmark][level] += count * weight

    return {k: dict(v) for k, v in benchmark_data.items()}

# ---------------------------------------------------------------------------
# Build plot arrays
# ---------------------------------------------------------------------------

def build_plot_data(
    benchmark_data: dict[str, dict[int, float]]
) -> tuple[list[str], np.ndarray, np.ndarray, int]:
    """
    Returns:
        benchmarks   – sorted benchmark labels
        fractions    – (n_benchmarks, n_levels) relative frequencies
        avg_occ      – (n_benchmarks,) weighted mean occupancy per benchmark
        max_level    – highest occupancy level with non-zero weight across all benchmarks
    """
    benchmarks = sorted(benchmark_data.keys())

    # Find the range of levels that actually carry weight
    max_level = 0
    for levels in benchmark_data.values():
        for lvl, cnt in levels.items():
            if cnt > 0:
                max_level = max(max_level, lvl)

    n_levels = max_level + 1
    n_bench = len(benchmarks)

    fractions = np.zeros((n_bench, n_levels))
    avg_occ = np.zeros(n_bench)

    for i, bm in enumerate(benchmarks):
        levels = benchmark_data[bm]
        total = sum(levels.values())
        if total == 0:
            continue
        for lvl in range(n_levels):
            cnt = levels.get(lvl, 0.0)
            fractions[i, lvl] = cnt / total
        avg_occ[i] = sum(lvl * levels.get(lvl, 0.0) for lvl in range(n_levels)) / total

    return benchmarks, fractions, avg_occ, max_level

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot(
    benchmarks: list[str],
    fractions: np.ndarray,
    avg_occ: np.ndarray,
    max_level: int,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    n_bench, n_levels = fractions.shape

    # Append an "Average" bar
    avg_fractions = fractions.mean(axis=0)          # simple mean across benchmarks
    overall_avg_occ = avg_occ.mean()

    all_fractions = np.vstack([fractions, avg_fractions])
    all_labels = benchmarks + ["Average"]
    all_avg_occ = np.append(avg_occ, overall_avg_occ)

    n_bars = len(all_labels)

    # Colour palette: use a continuous map for levels
    cmap = plt.get_cmap('tab20', n_levels) if n_levels <= 20 else plt.get_cmap('viridis', n_levels)
    colors = [cmap(i) for i in range(n_levels)]

    fig, ax = plt.subplots(figsize=(max(14, n_bars * 0.7), 6))

    bar_width = 0.6
    x = np.arange(n_bars)

    bottoms = np.zeros(n_bars)
    bars_per_level = []
    for lvl in range(n_levels):
        heights = all_fractions[:, lvl]
        b = ax.bar(x, heights, bar_width, bottom=bottoms,
                   color=colors[lvl], label=str(lvl), zorder=2)
        bars_per_level.append(b)
        bottoms += heights

    # Draw a vertical separator before the "Average" bar
    ax.axvline(x=n_bars - 1.5, color='black', linewidth=1.0, linestyle='--', zorder=3)

    # Annotate average occupancy above each bar
    #for i in range(n_bars):
    #    ax.text(x[i], 1.01, f"{all_avg_occ[i]:.3f}",
    #            ha='center', va='bottom', fontsize=7.5, rotation=90)

    # Axis labels & ticks
    ax.set_xticks(x)
    ax.set_xticklabels(all_labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Fraction of cycles")
    ax.set_title("Broadcast Queue Occupancy per Cycle\n(relative, weighted simpoints)")
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, zorder=0)
    ax.set_axisbelow(True)

    # Legend (occupancy levels)
    handles = [mpatches.Patch(color=colors[lvl], label=f"occ={lvl}") for lvl in range(n_levels)]
    ax.legend(handles=handles, title="Occupancy", bbox_to_anchor=(1.01, 1),
              loc='upper left', fontsize=7, ncol=1)

    plt.tight_layout()
    out_path = output_dir / "broadcast_queue_occupancy.png"
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"Saved plot to {out_path}")
    plt.close(fig)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Searching for stats.txt files under {BASE_DIR} …")
    benchmark_data = collect_benchmark_histograms(BASE_DIR)
    print(f"Found {len(benchmark_data)} benchmarks.")

    benchmarks, fractions, avg_occ, max_level = build_plot_data(benchmark_data)

    for bm, occ in zip(benchmarks, avg_occ):
        print(f"  {bm:30s}  avg_occ = {occ:.4f}")

    plot(benchmarks, fractions, avg_occ, max_level, OUTPUT_DIR)


if __name__ == "__main__":
    main()
