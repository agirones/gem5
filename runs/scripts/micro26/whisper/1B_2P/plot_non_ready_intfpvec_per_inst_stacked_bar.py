#!/usr/bin/env python3
"""
Stacked bar chart of nonReadyIntFpVecSrcOpsPerDispatchedInst for each
benchmark under runs/output/micro26/whisper/1B_2P.

Each bar shows the fraction of dispatched instructions that have 0, 1, 2, …
non-ready int/fp/vec source registers.  Levels >= AGG_THRESHOLD are folded
into a single bucket.
An extra "Average" bar at the right shows the cross-benchmark aggregate.

Stat name: system.cpu.iew.nonReadyIntFpVecSrcOpsPerDispatchedInst
"""

import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
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
STAT_PREFIX = "system.cpu.iew.nonReadyIntFpVecSrcOpsPerDispatchedInst"

# Levels >= this value are folded into a single "AGG+" bucket.
AGG_THRESHOLD = 8

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_weight(path: Path) -> float:
    """Return simpoint weight from directory name, defaulting to 1.0."""
    m = re.search(r'weight_([0-9]+\.[0-9]+)', str(path))
    return float(m.group(1)) if m else 1.0


def extract_benchmark(path: Path) -> str:
    """Return the benchmark name from the path.

    Expected layout:
        BASE_DIR / {benchmark} / {simpoint_dir} / m5out / stats.txt
    """
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
    Parse the nonReadyIntFpVecSrcOpsPerDispatchedInst histogram from a
    stats.txt.  Returns a dict mapping count level -> raw count.
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
    benchmark_data: dict[str, dict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )

    for sf in stats_files:
        benchmark = extract_benchmark(sf)
        weight = extract_weight(sf)
        counts = parse_histogram(sf)
        for level, count in counts.items():
            benchmark_data[benchmark][level] += count * weight

    return {k: dict(v) for k, v in benchmark_data.items()}

# ---------------------------------------------------------------------------
# Build stacked-bar arrays
# ---------------------------------------------------------------------------

def build_bar_data(
    benchmark_data: dict[str, dict[int, float]],
    agg_threshold: int,
) -> tuple[list[str], np.ndarray, list[str]]:
    """
    Returns:
        labels      – benchmark names + "Average"
        fractions   – 2-D array of shape (n_bins, n_benchmarks+1);
                      each column sums to 1 (fraction of dispatched insts)
        bin_labels  – label for each row ("0", "1", …, "{agg_threshold}+")
    """
    benchmarks = sorted(benchmark_data.keys())

    max_raw_level = 0
    for levels in benchmark_data.values():
        for lvl, cnt in levels.items():
            if cnt > 0:
                max_raw_level = max(max_raw_level, lvl)

    discrete_levels = list(range(min(agg_threshold, max_raw_level + 1)))
    has_agg = max_raw_level >= agg_threshold
    bin_labels = [str(l) for l in discrete_levels]
    if has_agg:
        bin_labels.append(f"{agg_threshold}+")

    n_bins = len(bin_labels)

    # Average: merge all levels.
    merged: dict[int, float] = defaultdict(float)
    for bm in benchmarks:
        for lvl, cnt in benchmark_data[bm].items():
            merged[lvl] += cnt

    all_bm_list = benchmarks + ["Average"]
    all_data = [benchmark_data[bm] for bm in benchmarks] + [dict(merged)]

    n_entries = len(all_bm_list)
    fractions = np.zeros((n_bins, n_entries))

    for col, levels in enumerate(all_data):
        total = sum(levels.values())
        if total == 0:
            continue
        for row, lbl in enumerate(bin_labels):
            if lbl.endswith("+"):
                val = sum(
                    cnt for lvl, cnt in levels.items()
                    if lvl >= agg_threshold
                )
            else:
                lvl = int(lbl)
                val = levels.get(lvl, 0.0)
            fractions[row, col] = val / total

    return all_bm_list, fractions, bin_labels

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot(
    labels: list[str],
    fractions: np.ndarray,
    bin_labels: list[str],
    output_dir: Path,
    agg_threshold: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    n_bins, n_entries = fractions.shape
    x = np.arange(n_entries)

    cmap = plt.cm.get_cmap('tab10', agg_threshold)
    colors = [cmap(i) for i in range(min(n_bins, agg_threshold))]
    if n_bins > agg_threshold:
        colors.append('dimgray')

    fig, ax = plt.subplots(figsize=(max(14, n_entries * 0.75), 6))

    bar_width = 0.7
    bottoms = np.zeros(n_entries)
    for row in range(n_bins):
        ax.bar(
            x, fractions[row], bar_width,
            bottom=bottoms,
            color=colors[row],
            label=bin_labels[row],
            zorder=2,
        )
        bottoms += fractions[row]

    # Separator before "Average"
    ax.axvline(x=n_entries - 1.5, color='black', linewidth=1.0,
               linestyle='--', zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylim(0, 1.0)
    ax.yaxis.set_major_formatter(
        matplotlib.ticker.PercentFormatter(xmax=1.0, decimals=0)
    )
    ax.set_ylabel("Fraction of dispatched instructions")
    ax.set_title(
        "Non-Ready Int/Fp/Vec Source Operands per Dispatched Instruction\n"
        "(stacked bar, fraction of dispatched instructions; weighted simpoints)"
    )
    ax.yaxis.grid(True, linestyle='--', alpha=0.4, zorder=0)
    ax.set_axisbelow(True)

    ax.legend(
        title="Non-ready\nint/fp/vec\nsrc ops",
        bbox_to_anchor=(1.01, 1),
        loc='upper left',
        fontsize=7,
        title_fontsize=7,
        framealpha=0.9,
    )

    plt.tight_layout()
    out_path = output_dir / "non_ready_intfpvec_per_inst_stacked_bar.png"
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"Saved plot to {out_path}")
    plt.close(fig)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Searching for stats.txt files under {BASE_DIR} …")
    benchmark_data = collect_benchmark_histograms(BASE_DIR)
    if not benchmark_data:
        print("No data found. Has the simulation been run with the new stat?")
        return
    print(f"Found {len(benchmark_data)} benchmarks.")

    labels, fractions, bin_labels = build_bar_data(benchmark_data, AGG_THRESHOLD)
    print(f"Bins: {bin_labels}")

    for lbl, col in zip(labels, fractions.T):
        dominant = bin_labels[int(np.argmax(col))]
        print(f"  {lbl:30s}  dominant level = {dominant}")

    plot(labels, fractions, bin_labels, OUTPUT_DIR, AGG_THRESHOLD)


if __name__ == "__main__":
    main()
