#!/usr/bin/env python3
"""
Violin plot of nonReadyIntFpVecSrcOpsPerDispatchedInst for each benchmark
under runs/output/micro26/whisper/1B_2P.

Each violin shows the full distribution (KDE over discrete levels) of the
fraction of dispatched instructions at each non-ready int/fp/vec source
operand count.  A white dot marks the weighted mean; the thick bar covers
the IQR; the thin whisker covers ±1 std; orange and red ticks mark the
90th and 95th percentiles.
An extra "Average" violin at the right shows the cross-benchmark aggregate.

Stat name: system.cpu.iew.nonReadyIntFpVecSrcOpsPerDispatchedInst
"""

import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import gaussian_kde

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
    Parse the nonReadyIntFpVecSrcOpsPerDispatchedInst histogram.
    Returns a dict mapping count level -> raw count.
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
# Build plot arrays
# ---------------------------------------------------------------------------

def build_plot_data(
    benchmark_data: dict[str, dict[int, float]]
) -> tuple[list[str], list[np.ndarray], np.ndarray, np.ndarray, int]:
    """
    Returns:
        benchmarks  – sorted benchmark labels (plus "Average" appended)
        samples     – list of 1-D arrays; each is a weighted sample sequence
                      suitable for KDE (one entry per benchmark + average)
        means       – weighted mean per entry
        stds        – weighted std per entry
        max_level   – highest level with non-zero weight
    """
    benchmarks = sorted(benchmark_data.keys())

    max_level = 0
    for levels in benchmark_data.values():
        for lvl, cnt in levels.items():
            if cnt > 0:
                max_level = max(max_level, lvl)

    def _stats(levels: dict[int, float]):
        total = sum(levels.values())
        if total == 0:
            return np.array([0.0]), 0.0, 0.0
        N = 10_000
        pts = []
        for lvl in range(max_level + 1):
            cnt = levels.get(lvl, 0.0)
            n = int(round(cnt / total * N))
            pts.extend([lvl] * n)
        if not pts:
            pts = [0]
        arr = np.array(pts, dtype=float)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        return arr, mean, std

    all_labels = benchmarks[:]
    all_samples = []
    all_means = []
    all_stds = []

    for bm in benchmarks:
        arr, mean, std = _stats(benchmark_data[bm])
        all_samples.append(arr)
        all_means.append(mean)
        all_stds.append(std)

    # Average: merge all levels.
    merged: dict[int, float] = defaultdict(float)
    for bm in benchmarks:
        for lvl, cnt in benchmark_data[bm].items():
            merged[lvl] += cnt
    avg_arr, avg_mean, avg_std = _stats(dict(merged))
    all_labels.append("Average")
    all_samples.append(avg_arr)
    all_means.append(avg_mean)
    all_stds.append(avg_std)

    return (
        all_labels,
        all_samples,
        np.array(all_means),
        np.array(all_stds),
        max_level,
    )

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def _draw_violin(ax, x_pos: float, samples: np.ndarray, mean: float, std: float,
                 color: str, width: float = 0.7) -> None:
    """Draw a single violin at x_pos using KDE over samples."""
    if len(set(samples)) == 1:
        ax.plot([x_pos - width / 2, x_pos + width / 2],
                [samples[0], samples[0]], color=color, lw=2)
        ax.scatter([x_pos], [mean], color='white', s=18, zorder=5)
        return

    kde = gaussian_kde(samples, bw_method=0.3)
    y_grid = np.linspace(samples.min(), samples.max(), 500)
    density = kde(y_grid)
    density = density / density.max() * (width / 2)

    ax.fill_betweenx(y_grid, x_pos - density, x_pos + density,
                     color=color, alpha=0.75, zorder=2)
    ax.plot(x_pos - density, y_grid, color=color, lw=0.6, alpha=0.9, zorder=3)
    ax.plot(x_pos + density, y_grid, color=color, lw=0.6, alpha=0.9, zorder=3)

    # IQR thick bar
    q25, q75 = np.percentile(samples, [25, 75])
    ax.plot([x_pos, x_pos], [q25, q75], color='black', lw=4,
            solid_capstyle='round', zorder=4)
    # ±1 std thin whisker
    ax.plot([x_pos, x_pos], [mean - std, mean + std],
            color='black', lw=1.5, solid_capstyle='round', zorder=4)
    # 90th and 95th percentile tick marks
    tick_hw = width * 0.30
    for pct, pct_color, pct_lw in [(90, 'darkorange', 1.5), (95, 'crimson', 1.5)]:
        pval = np.percentile(samples, pct)
        ax.plot([x_pos - tick_hw, x_pos + tick_hw], [pval, pval],
                color=pct_color, lw=pct_lw, zorder=6)
    # Mean dot
    ax.scatter([x_pos], [mean], color='white', edgecolors='black',
               s=30, zorder=7, linewidths=0.8)


def plot(
    labels: list[str],
    samples: list[np.ndarray],
    means: np.ndarray,
    stds: np.ndarray,
    max_level: int,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    n = len(labels)
    x = np.arange(n)

    colors = ['steelblue'] * (n - 1) + ['tomato']

    fig, ax = plt.subplots(figsize=(max(14, n * 0.75), 6))

    for i, (lbl, samp, mean, std) in enumerate(zip(labels, samples, means, stds)):
        _draw_violin(ax, x[i], samp, mean, std, color=colors[i])

    ax.axvline(x=n - 1.5, color='black', linewidth=1.0, linestyle='--', zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylim(-0.5, max_level + 0.5)
    ax.set_yticks(range(max_level + 1))
    ax.set_ylabel("Non-ready int/fp/vec source operands per instruction")
    ax.set_title(
        "Non-Ready Int/Fp/Vec Source Operands per Dispatched Instruction\n"
        "(violin = KDE, bar = IQR, whisker = ±1 std, dot = mean; weighted simpoints)"
    )
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, zorder=0)
    ax.set_axisbelow(True)

    import matplotlib.lines as mlines
    legend_handles = [
        mlines.Line2D([], [], color='black', lw=4, label='IQR (25–75%)'),
        mlines.Line2D([], [], color='black', lw=1.5, label='±1 std'),
        mlines.Line2D([], [], color='darkorange', lw=1.5, label='90th percentile'),
        mlines.Line2D([], [], color='crimson', lw=1.5, label='95th percentile'),
        mlines.Line2D([], [], marker='o', color='w', markerfacecolor='white',
                      markeredgecolor='black', markersize=6, label='Mean'),
    ]
    ax.legend(handles=legend_handles, fontsize=7, loc='upper right')

    for i, mean in enumerate(means):
        ax.text(x[i], max_level + 0.35, f"{mean:.2f}",
                ha='center', va='bottom', fontsize=6.5, color='dimgray')

    plt.tight_layout()
    out_path = output_dir / "non_ready_intfpvec_per_inst_violin.png"
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

    labels, samples, means, stds, max_level = build_plot_data(benchmark_data)

    for lbl, mean, std in zip(labels[:-1], means[:-1], stds[:-1]):
        print(f"  {lbl:30s}  mean = {mean:.4f}  std = {std:.4f}")
    print(f"  {'Average':30s}  mean = {means[-1]:.4f}  std = {stds[-1]:.4f}")

    plot(labels, samples, means, stds, max_level, OUTPUT_DIR)


if __name__ == "__main__":
    main()
