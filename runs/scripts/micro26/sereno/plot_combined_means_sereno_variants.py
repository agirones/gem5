#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ figure with two side-by-side stacked bar charts:

  (a) Normalized performance   — harmonic-mean IPC change (%) relative to baseline
  (b) Comparisons Reduction    — weighted-mean comparisons-per-instruction reduction (%)

Each chart has three bars, one per Sereno variant:

  A / Checkpointing      : sereno/ckpt
  B / Recovery Broadcast : sereno/sqbcast
  C / Guarded Wakeup     : sereno/stale

IPC means  : system.cpu.ipc weighted per benchmark, harmonic mean over benchmarks (plot_ipc_comparison.py).
Comp means : harmonic mean of per-benchmark rates for baseline and variant (plot_comparisons_relative.py).

Output: runs/output/micro26/graphs/combined_means_sereno_variants.tex
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path("/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU")

BASELINE_DIR = ROOT / "runs/output/micro26/baseline/12B_-1P"

APPROACHES: dict[str, Path] = {
    "ckpt":    ROOT / "runs/output/micro26/sereno/ckpt",
    "sqbcast": ROOT / "runs/output/micro26/sereno/sqbcast",
    "stale":   ROOT / "runs/output/micro26/sereno/stale",
}

OUTPUT_DIR = ROOT / "runs/output/micro26/graphs"
OUTPUT_TEX = OUTPUT_DIR / "combined_means_sereno_variants.tex"

# Stats for IPC
IPC_STAT    = "system.cpu.ipc"

# Stats for comparisons reduction
COMP_STAT  = "system.cpu.iew.iqWakeupComparisons"
INSTR_STAT = "system.cpu.commitStats0.numInsts"

# Human-readable legend labels (order matches APPROACHES)
DISPLAY_NAMES: dict[str, str] = {
    "ckpt":    "Checkpointing",
    "sqbcast": "Recovery Broadcast",
    "stale":   "Guarded Wakeup",
}

# Symbolic x-coord assigned to each approach
SYM_COORDS: dict[str, str] = {
    "ckpt":    "ckpt",
    "sqbcast": "sqbcast",
    "stale":   "stale",
}

# Color name and RGB values per approach
BAR_COLORS: dict[str, tuple[str, int, int, int]] = {
    "ckpt":    ("clrSereno",        86, 180, 233),
    "sqbcast": ("clrSerenoSqBcast", 213,  94,   0),
    "stale":   ("clrSerenoStale",   240, 228,  66),
}

# y-axis limits for each chart (adjust if actual data falls outside)
IPC_YMIN,  IPC_YMAX  = -5, 0
COMP_YMIN, COMP_YMAX = 0, 100

# ---------------------------------------------------------------------------
# Shared parsing helpers
# ---------------------------------------------------------------------------

def extract_weight(path: Path) -> float:
    m = re.search(r'weight_([0-9]+\.[0-9]+)', str(path))
    return float(m.group(1)) if m else 1.0


def extract_benchmark(stats_file: Path) -> str:
    """Expected layout: {base_dir}/width8/{benchmark}/{simpoint_dir}/m5out/stats.txt"""
    return stats_file.parent.parent.parent.name


def _stats_files(base_dir: Path) -> list[Path]:
    return sorted(
        f for f in base_dir.glob("**/stats.txt")
        if "sensibility_analysis" not in f.parts
    )

# ---------------------------------------------------------------------------
# IPC collection  (mirrors plot_ipc_comparison.py)
# Uses system.cpu.ipc directly; weighted IPC per benchmark; HM of benchmarks.
# ---------------------------------------------------------------------------

def _parse_ipc(sf: Path) -> Optional[float]:
    """Return the IPC value from the final stats dump."""
    in_dump = False
    last_ipc: Optional[float] = None
    cur_ipc:  Optional[float] = None
    try:
        with open(sf, 'r', errors='replace') as f:
            for line in f:
                if '---------- Begin Simulation Statistics ----------' in line:
                    in_dump = True
                    cur_ipc = None
                    continue
                if '---------- End Simulation Statistics   ----------' in line:
                    if cur_ipc is not None:
                        last_ipc = cur_ipc
                    in_dump = False
                    continue
                if in_dump and line.startswith(IPC_STAT):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            cur_ipc = float(parts[1])
                        except ValueError:
                            pass
    except OSError:
        return None
    return last_ipc


def collect_ipc(base_dir: Path) -> dict[str, float]:
    """Return {benchmark: weighted_IPC} using system.cpu.ipc."""
    files = _stats_files(base_dir)
    if not files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}

    w_ipc: dict[str, float] = defaultdict(float)
    w_sum: dict[str, float] = defaultdict(float)

    for sf in files:
        ipc = _parse_ipc(sf)
        if ipc is None:
            print(f"  WARNING: could not parse IPC from {sf}")
            continue
        bm     = extract_benchmark(sf)
        weight = extract_weight(sf)
        w_ipc[bm] += weight * ipc
        w_sum[bm] += weight

    return {bm: w_ipc[bm] / w_sum[bm] for bm in w_ipc if w_sum[bm] > 0}


def harmonic_mean(values: list[float]) -> float:
    pos = [v for v in values if v > 0]
    if not pos:
        return float('nan')
    return len(pos) / sum(1.0 / v for v in pos)

# ---------------------------------------------------------------------------
# Comparisons-reduction collection  (mirrors plot_comparisons_relative_sereno_variants.py)
# ---------------------------------------------------------------------------

def _parse_two_stats(sf: Path, stat_a: str, stat_b: str) -> tuple[Optional[float], Optional[float]]:
    in_dump = False
    last_a: Optional[float] = None
    last_b: Optional[float] = None
    cur_a:  Optional[float] = None
    cur_b:  Optional[float] = None
    try:
        with open(sf, 'r', errors='replace') as f:
            for line in f:
                if '---------- Begin Simulation Statistics ----------' in line:
                    in_dump = True
                    cur_a = cur_b = None
                    continue
                if '---------- End Simulation Statistics   ----------' in line:
                    if cur_a is not None:
                        last_a = cur_a
                    if cur_b is not None:
                        last_b = cur_b
                    in_dump = False
                    continue
                if not in_dump:
                    continue
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == stat_a and len(parts) >= 2:
                    try:
                        cur_a = float(parts[1])
                    except ValueError:
                        pass
                elif parts[0] == stat_b and len(parts) >= 2:
                    try:
                        cur_b = float(parts[1])
                    except ValueError:
                        pass
    except OSError:
        return None, None
    return last_a, last_b


def collect_comp_rate(base_dir: Path) -> dict[str, float]:
    """Return {benchmark: weighted_comparisons_per_instruction}."""
    files = _stats_files(base_dir)
    if not files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}

    w_rate:  dict[str, float] = defaultdict(float)
    w_sum:   dict[str, float] = defaultdict(float)

    for sf in files:
        comps, insts = _parse_two_stats(sf, COMP_STAT, INSTR_STAT)
        if comps is None:
            print(f"  WARNING: could not parse {COMP_STAT} from {sf}")
            continue
        if insts is None or insts == 0:
            print(f"  WARNING: could not parse {INSTR_STAT} (or zero) from {sf}")
            continue
        bm     = extract_benchmark(sf)
        weight = extract_weight(sf)
        w_rate[bm] += weight * (comps / insts)
        w_sum[bm]  += weight

    return {bm: w_rate[bm] / w_sum[bm] for bm in w_rate if w_sum[bm] > 0}

# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------

def _addplots(approach_names: list[str], values: dict[str, float], legend: bool) -> str:
    """
    Build \\addplot lines for one axis.  Each approach owns one x position;
    all other positions are 0 so the stacked bars don't actually stack.
    If *legend* is True, include \\addlegendentry for each plot.
    """
    lines: list[str] = []
    for name in approach_names:
        cname = BAR_COLORS[name][0]
        coords = " ".join(
            f"({SYM_COORDS[n]},{values.get(name, 0.0):.6f})"
            if n == name else
            f"({SYM_COORDS[n]},0)"
            for n in approach_names
        )
        entry = (
            f"        \\addplot[fill={cname}, draw={cname}!60!black, line width=0.3pt] coordinates {{{coords}}};\n"
            + (f"        \\addlegendentry{{{DISPLAY_NAMES[name]}}}" if legend else "")
        )
        lines.append(entry)
    return "\n\n".join(lines)


def generate_tex(
    ipc_means:  dict[str, float],
    comp_means: dict[str, float],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    approach_names = list(APPROACHES.keys())
    sym_coords_str = ", ".join(SYM_COORDS[n] for n in approach_names)

    define_colors = "".join(
        f"\\definecolor{{{BAR_COLORS[n][0]}}}{{RGB}}{{{BAR_COLORS[n][1]},{BAR_COLORS[n][2]},{BAR_COLORS[n][3]}}}\n"
        for n in approach_names
    )

    ipc_plots  = _addplots(approach_names, ipc_means,  legend=True)
    comp_plots = _addplots(approach_names, comp_means, legend=False)

    tex = (
        r"\documentclass[tikz]{standalone}" "\n"
        r"\usepackage{pgfplots}" "\n"
        r"\pgfplotsset{compat=1.18}" "\n"
        r"\usetikzlibrary{calc}" "\n"
        "\n"
        + define_colors +
        "\n"
        r"\begin{document}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"    \begin{axis}[" "\n"
        r"        name=plot1," "\n"
        r"        ybar stacked," "\n"
        r"        enlarge x limits     = 0.33," "\n"
        r"        width=0.25\columnwidth," "\n"
        r"        height=3cm," "\n"
        r"        scale only axis," "\n"
        f"        symbolic x coords={{{sym_coords_str}}},\n"
        r"        xtick=\empty," "\n"
        r"        xlabel={(a) Normalized performance}," "\n"
        r"        tick label style={font=\footnotesize}," "\n"
        r"        label style={font=\scriptsize}," "\n"
        r"        yticklabel      = {\pgfmathprintnumber{\tick}\%}," "\n"
        f"        ymin={IPC_YMIN}, ymax={IPC_YMAX},\n"
        r"        grid=major," "\n"
        r"        ymajorgrids=true," "\n"
        r"        grid style      = {dashed, gray!30}," "\n"
        r"        axis line style = {gray!60}," "\n"
        r"        tick style      = {gray!60}," "\n"
        r"        extra y ticks={0}," "\n"
        r"        extra y tick style={grid style={black, dashed}}," "\n"
        r"        legend style    = {" "\n"
        r"            at={(0.5,1.05)}, anchor=south," "\n"
        r"            font=\scriptsize," "\n"
        r"            cells={anchor=west}," "\n"
        r"            draw=none," "\n"
        r"            /tikz/every even column/.append style={column sep=6pt}," "\n"
        r"        }," "\n"
        r"        legend columns  = -1," "\n"
        r"        legend to name=sharedLegend," "\n"
        r"        legend style={font=\footnotesize}," "\n"
        r"    ]" "\n"
        + ipc_plots + "\n"
        r"    \end{axis}" "\n"
        "\n"
        r"    \begin{axis}[" "\n"
        r"        name=plot2," "\n"
        r"        at={($(plot1.east) + (0.9cm,0)$)}," "\n"
        r"        anchor=west," "\n"
        r"        ybar stacked," "\n"
        r"        enlarge x limits     = 0.33," "\n"
        r"        width=0.25\columnwidth," "\n"
        r"        height=3cm," "\n"
        r"        scale only axis," "\n"
        f"        symbolic x coords={{{sym_coords_str}}},\n"
        r"        xtick=\empty," "\n"
        r"        xlabel={(b) Comparisons Reduction}," "\n"
        r"        yticklabel      = {\pgfmathprintnumber{\tick}\%}," "\n"
        f"        ymin={COMP_YMIN}, ymax={COMP_YMAX},\n"
        r"        grid=major," "\n"
        r"        ymajorgrids=true," "\n"
        r"        grid style      = {dashed, gray!30}," "\n"
        r"        axis line style = {gray!60}," "\n"
        r"        tick style      = {gray!60}," "\n"
        r"        tick label style={font=\footnotesize}," "\n"
        r"        label style={font=\scriptsize}," "\n"
        r"    ]" "\n"
        + comp_plots + "\n"
        r"    \end{axis}" "\n"
        "\n"
        r"    % Place the legend centered above the two plots" "\n"
        r"    \node[anchor=south] at ($(plot1.north east)!0.5!(plot2.north west) - (0,0)$) {\ref{sharedLegend}};" "\n"
        "\n"
        r"\end{tikzpicture}" "\n"
        r"\end{document}" "\n"
    )

    with open(output_path, 'w') as f:
        f.write(tex)
    print(f"Saved {output_path}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not BASELINE_DIR.exists():
        print(f"ERROR: baseline directory not found: {BASELINE_DIR}")
        return

    # --- IPC harmonic-mean change (mirrors plot_ipc_comparison.py) ---
    # Use system.cpu.ipc; weighted IPC per benchmark; HM over per-benchmark IPCs.
    print("Collecting IPC for baseline …")
    baseline_ipc = collect_ipc(BASELINE_DIR)
    print(f"  → {len(baseline_ipc)} benchmarks")
    all_bms_ipc = sorted(baseline_ipc.keys())
    hm_baseline_ipc = harmonic_mean([baseline_ipc[bm] for bm in all_bms_ipc])

    ipc_means: dict[str, float] = {}
    for name, base_dir in APPROACHES.items():
        if not base_dir.exists():
            print(f"SKIP {name}: {base_dir} not found")
            continue
        print(f"Collecting IPC for {name} …")
        d = collect_ipc(base_dir)
        common = [bm for bm in all_bms_ipc if bm in d]
        hm_opt = harmonic_mean([d[bm] for bm in common])
        ipc_means[name] = (hm_opt / hm_baseline_ipc - 1.0) * 100.0 if hm_baseline_ipc > 0 else float('nan')
        print(f"  → {len(d)} benchmarks  |  harmonic-mean IPC change = {ipc_means[name]:.4f}%")

    # --- Comparisons harmonic-mean reduction (mirrors plot_comparisons_relative.py) ---
    # HM of per-benchmark rates for both baseline and optimized.
    print("\nCollecting comparison rates for baseline …")
    baseline_comp = collect_comp_rate(BASELINE_DIR)
    print(f"  → {len(baseline_comp)} benchmarks")
    all_bms_comp = sorted(baseline_comp.keys())
    hm_baseline_comp = harmonic_mean([baseline_comp[bm] for bm in all_bms_comp])

    comp_means: dict[str, float] = {}
    for name, base_dir in APPROACHES.items():
        if not base_dir.exists():
            continue
        print(f"Collecting comparison rates for {name} …")
        d = collect_comp_rate(base_dir)
        opt_vals = [d[bm] for bm in all_bms_comp if bm in d]
        hm_opt = harmonic_mean(opt_vals)
        comp_means[name] = (1.0 - hm_opt / hm_baseline_comp) * 100.0 if hm_baseline_comp > 0 else float('nan')
        print(f"  → harmonic-mean comparisons reduction = {comp_means[name]:.4f}%")

    # Summary table
    print(f"\n{'Approach':<14} {'IPC change':>12} {'Comp reduction':>16}")
    print("-" * 44)
    for name in APPROACHES:
        ipc  = ipc_means.get(name, float('nan'))
        comp = comp_means.get(name, float('nan'))
        print(f"{DISPLAY_NAMES[name]:<14} {ipc:>11.4f}% {comp:>15.4f}%")

    generate_tex(ipc_means, comp_means, OUTPUT_TEX)


if __name__ == "__main__":
    main()
