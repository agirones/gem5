#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) grouped bar chart showing the
harmonic mean IPC for each (broadcastMax, dependentsThreshold) configuration
in the Sereno sensitivity analysis.

  X-axis  : dependentsThreshold values (−1, 0, 1, 2, 3, 4)
  Bars    : one bar group per x-tick, with 5 bars for broadcastMax 1–5
  Y-axis  : harmonic mean IPC across all benchmarks (weighted per simpoint)

Data source
-----------
  system.cpu.ipc

Read from:
  runs/output/micro26/sereno/ckpt/sensibility_analysis/
    bmax{N}_dt{M}/width8/{benchmark}/{simpoint}/m5out/stats.txt

Per-benchmark IPC: weighted arithmetic mean over simpoints
  (weights from the simpoint directory name, e.g. weight_0.31966).
Overall IPC: harmonic mean of per-benchmark IPC values.

Output
------
  runs/output/micro26/sereno/ckpt/sensibility_analysis/ipc_sensitivity.tex
"""

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT     = Path(__file__).resolve().parents[6]   # .../gem5-NTNU/
SENS_DIR = ROOT / "runs/output/micro26/sereno/ckpt/sensibility_analysis"
OUTPUT_TEX = SENS_DIR / "ipc_sensitivity.tex"

INSTS_STAT  = "system.cpu.commitStats0.numInsts"
CYCLES_STAT = "system.cpu.numCycles"

BASELINE_DIR = ROOT / "runs/output/micro26/baseline/12B_-1P"

BROADCAST_MAX_VALUES        = list(range(1, 6))         # 1 … 5
DEPENDENTS_THRESHOLD_VALUES = list(range(0, 5))       # 0 … 4

# Set to a benchmark name (e.g. "mcf_r") to print detailed debug information
# for that benchmark only, or None to disable all debug output.
DEBUG_BENCHMARK: Optional[str] = "mcf_r"


# ---------------------------------------------------------------------------
# Visual style: one entry per broadcastMax value (1–5)
# ---------------------------------------------------------------------------
# (color_name, R, G, B, pgfplots_pattern | None)
BAR_STYLES: list[tuple[str, int, int, int, Optional[str]]] = [
    ("clrBmax1",  230, 159, 0, "north east lines"),                 # Tableau blue  – solid
    ("clrBmax2", 86, 180, 233, None),   # Tableau orange
    ("clrBmax3", 0, 158, 115, "crosshatch"),          # Tableau green
    ("clrBmax4", 213, 94, 0, "crosshatch dots"),    # Tableau red
    ("clrBmax5", 148, 103, 189, "horizontal lines"),   # Tableau purple
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_weight(path: Path) -> float:
    """Return simpoint weight from directory name (defaults to 1.0)."""
    m = re.search(r'weight_([0-9]+(?:\.[0-9]+)?)', str(path))
    return float(m.group(1)) if m else 1.0


def parse_stats(stats_file: Path, _dbg: bool = False) -> Optional[tuple[float, float]]:
    """Return (insts, cycles) from the final stats dump section."""
    in_dump       = False
    last_pair: Optional[tuple[float, float]] = None
    cur_insts: Optional[float]  = None
    cur_cycles: Optional[float] = None

    try:
        with open(stats_file, 'r', errors='replace') as f:
            for line in f:
                if '---------- Begin Simulation Statistics ----------' in line:
                    in_dump    = True
                    cur_insts  = None
                    cur_cycles = None
                    continue
                if '---------- End Simulation Statistics   ----------' in line:
                    if cur_insts is not None and cur_cycles is not None:
                        last_pair = (cur_insts, cur_cycles)
                        if _dbg:
                            ipc = cur_insts / cur_cycles
                            print(f"    [parse]  dump end → insts={cur_insts:.0f}  cycles={cur_cycles:.0f}  ipc={ipc:.6f}")
                    else:
                        if _dbg:
                            print(f"    [parse]  dump end → incomplete (insts={cur_insts}, cycles={cur_cycles}), skipping")
                    in_dump = False
                    continue
                if in_dump:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            if line.startswith(INSTS_STAT):
                                cur_insts = float(parts[1])
                            elif line.startswith(CYCLES_STAT):
                                cur_cycles = float(parts[1])
                        except ValueError:
                            pass
    except OSError:
        return None

    if _dbg and last_pair is None:
        print(f"    [parse]  {stats_file} → no valid dump found")
    return last_pair


def collect_harmonic_mean_ipc(config_dir: Path) -> Optional[float]:
    """
    Walk *config_dir*/width8/ and return the harmonic mean IPC across all
    benchmarks.  Per-benchmark IPC is computed as:
        IPC_bm = sum(weight_i * insts_i) / sum(weight_i * cycles_i)
    The overall metric is the harmonic mean of per-benchmark IPC values.
    Returns None if no stats were found.
    """
    stats_files = sorted(config_dir.glob("width*/*/*/m5out/stats.txt"))
    if not stats_files:
        return None

    if DEBUG_BENCHMARK is not None:
        print(f"  [collect]  {config_dir.name}: found {len(stats_files)} stats file(s)")

    weighted_insts:  dict[str, float] = defaultdict(float)
    weighted_cycles: dict[str, float] = defaultdict(float)

    for sf in stats_files:
        # path layout: {config_dir}/width{W}/{benchmark}/{simpoint}/m5out/stats.txt
        benchmark = sf.parent.parent.parent.name
        simpoint  = sf.parent.parent.name
        weight    = extract_weight(sf.parent.parent)    # simpoint dir
        _dbg      = (DEBUG_BENCHMARK is not None and benchmark == DEBUG_BENCHMARK)

        if _dbg:
            print(f"  [collect]  benchmark={benchmark}  simpoint={simpoint}  weight={weight}")

        pair = parse_stats(sf, _dbg)
        if pair is None:
            if _dbg:
                print(f"    [collect]  SKIP: parse_stats returned None for {sf}")
            continue
        insts, cycles = pair
        if cycles <= 0:
            if _dbg:
                print(f"    [collect]  SKIP: cycles={cycles} <= 0")
            continue

        if _dbg:
            print(f"    [collect]  raw insts={insts:.0f}  cycles={cycles:.0f}  raw_ipc={insts/cycles:.6f}")
            print(f"    [collect]  contribution: w*insts={weight*insts:.2f}  w*cycles={weight*cycles:.2f}")

        weighted_insts[benchmark]  += weight * insts
        weighted_cycles[benchmark] += weight * cycles

    if DEBUG_BENCHMARK is not None:
        print(f"  [collect]  per-benchmark weighted sums:")
        for bm in sorted(weighted_insts):
            wi  = weighted_insts[bm]
            wc  = weighted_cycles[bm]
            ipc = wi / wc if wc > 0 else float('nan')
            # detailed row only for the target benchmark; summary for others
            if bm == DEBUG_BENCHMARK:
                print(f"    benchmark={bm:30s}  w_insts={wi:.2f}  w_cycles={wc:.2f}  ipc={ipc:.6f}  <<< target")
            else:
                print(f"    benchmark={bm:30s}  ipc={ipc:.6f}")

    per_bench = [
        weighted_insts[bm] / weighted_cycles[bm]
        for bm in weighted_insts
        if weighted_cycles[bm] > 0
    ]

    if not per_bench:
        return None

    hm = len(per_bench) / sum(1.0 / v for v in per_bench)
    if DEBUG_BENCHMARK is not None:
        print(f"  [collect]  harmonic mean over {len(per_bench)} benchmarks = {hm:.6f}")
    return hm


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_all() -> dict[tuple[int, int], Optional[float]]:
    """
    Returns a mapping (bmax, dt) -> normalized_harmonic_mean_IPC for every
    configuration directory that exists under SENS_DIR.  Each value is the
    harmonic mean IPC of that configuration divided by the harmonic mean IPC
    of the baseline.
    """
    # Compute baseline harmonic mean first.
    if not BASELINE_DIR.exists():
        print(f"  WARNING: baseline directory not found: {BASELINE_DIR}", file=sys.stderr)
        baseline_hm = None
    else:
        if DEBUG_BENCHMARK is not None:
            print(f"\n[collect_all] Computing baseline HM IPC from {BASELINE_DIR}")
        baseline_hm = collect_harmonic_mean_ipc(BASELINE_DIR)
        if baseline_hm is None:
            print(f"  WARNING: no stats found in baseline {BASELINE_DIR}", file=sys.stderr)
        elif DEBUG_BENCHMARK is not None:
            print(f"[collect_all] Baseline harmonic mean IPC = {baseline_hm:.6f}\n")

    data: dict[tuple[int, int], Optional[float]] = {}
    for bmax in BROADCAST_MAX_VALUES:
        for dt in DEPENDENTS_THRESHOLD_VALUES:
            config_dir = SENS_DIR / f"bmax{bmax}_dt{dt}"
            if not config_dir.exists():
                print(f"  WARNING: directory not found: {config_dir}", file=sys.stderr)
                data[(bmax, dt)] = None
            else:
                if DEBUG_BENCHMARK is not None:
                    print(f"\n[collect_all] Computing HM IPC for bmax={bmax} dt={dt}")
                hm = collect_harmonic_mean_ipc(config_dir)
                if hm is None:
                    print(f"  WARNING: no stats found in {config_dir}", file=sys.stderr)
                if hm is not None and baseline_hm is not None and baseline_hm > 0:
                    normalized = (hm / baseline_hm) * 100.0
                    if DEBUG_BENCHMARK is not None:
                        print(f"[collect_all] bmax={bmax} dt={dt}: hm_ipc={hm:.6f}  baseline={baseline_hm:.6f}  normalized={normalized:.2f}%")
                    data[(bmax, dt)] = normalized
                else:
                    data[(bmax, dt)] = None
    return data


# ---------------------------------------------------------------------------
# LaTeX generation
# ---------------------------------------------------------------------------

def _dt_coord(dt: int) -> str:
    """Symbolic coordinate name for a dependentsThreshold value."""
    return f"dt_neg{abs(dt)}" if dt < 0 else f"dt_{dt}"


def _dt_label(dt: int) -> str:
    """X-tick display label (uses LaTeX minus sign for negative values)."""
    return f"$-{abs(dt)}$" if dt < 0 else str(dt)


def generate_tex(data: dict[tuple[int, int], Optional[float]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sym_coords   = ", ".join(_dt_coord(dt) for dt in DEPENDENTS_THRESHOLD_VALUES)
    xticklabels  = ", ".join(_dt_label(dt) for dt in DEPENDENTS_THRESHOLD_VALUES)

    # Collect all valid IPC values to set y-axis limits automatically.
    valid_ipc = [v for v in data.values() if v is not None]
    if valid_ipc:
        ymin_auto = min(valid_ipc)
        ymax_auto = max(valid_ipc)
        margin    = (ymax_auto - ymin_auto) * 0.1 if ymax_auto != ymin_auto else 1.0
        ymin = round(ymin_auto - margin - 1.0, 1)
        ymax = round(ymax_auto + margin + 1.0, 1)
    else:
        ymin, ymax = 0.0, 120.0

    # definecolor lines
    define_colors = ""
    for cname, r, g, b, _ in BAR_STYLES:
        define_colors += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    # \addplot blocks – one per broadcastMax value
    addplot_blocks: list[str] = []
    for i, (bmax, style) in enumerate(zip(BROADCAST_MAX_VALUES, BAR_STYLES)):
        cname, _, _, _, pattern = style
        coords: list[str] = []
        for dt in DEPENDENTS_THRESHOLD_VALUES:
            hm = data.get((bmax, dt))
            if hm is not None:
                coords.append(f"({_dt_coord(dt)}, {hm:.6f})")

        coord_body   = "\n        ".join(coords)
        label        = f"{bmax} broadcast port{'s' if bmax != 1 else ''}"
        postaction   = (
            f",\n        postaction={{pattern={pattern}, draw=black}}"
            if pattern else ""
        )
        addplot_blocks.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw={cname}!60!black,\n"
            f"        line width=0.4pt{postaction},\n"
            f"    ] coordinates {{\n"
            f"        {coord_body}\n"
            f"    }};\n"
            f"    \\addlegendentry{{{label}}}"
        )

    addplot_str = "\n\n".join(addplot_blocks)

    tex = (
        r"\documentclass[tikz]{standalone}" "\n"
        r"\usepackage{pgfplots}" "\n"
        r"\pgfplotsset{compat=1.18}" "\n"
        r"\usetikzlibrary{patterns}" "\n"
        "\n"
        + define_colors +
        "\n"
        r"\pgfplotsset{" "\n"
        r"    legend image code/.code={" "\n"
        r"        \draw[#1, draw=black, line width=0.4pt]" "\n"
        r"            (0pt,-1pt) rectangle (5pt,4pt);" "\n"
        r"    }," "\n"
        r"}" "\n"
        "\n"
        r"\begin{document}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"\begin{axis}[" "\n"
        r"    ybar            = 2pt," "\n"
        r"    area legend," "\n"
        r"    bar width       = 7pt," "\n"
        r"    width           = 12cm," "\n"
        r"    height          = 7cm," "\n"
        r"    enlarge x limits= 0.12," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    x tick label style = {font=\normalsize}," "\n"
        r"    xlabel          = {Number of dependent threshold}," "\n"
        r"    xlabel style    = {font=\normalsize, yshift=-4pt}," "\n"
        f"    ymin            = {ymin:.1f},\n"
        f"    ymax            = {ymax:.1f},\n"
        r"    ylabel          = {Normalized performance}," "\n"
        r"    ylabel style    = {font=\normalsize}," "\n"
        r"    yticklabel      = {$\pgfmathprintnumber{\tick}$\,\%}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    legend style    = {" "\n"
        r"        at={(0.5,1.03)}, anchor=south," "\n"
        r"        font=\normalsize," "\n"
        r"        cells={anchor=west}," "\n"
        r"        legend columns=5," "\n"
        r"        column sep=4pt," "\n"
        r"    }," "\n"
        r"]" "\n"
        "\n"
        + addplot_str + "\n"
        "\n"
        r"\end{axis}" "\n"
        r"\end{tikzpicture}" "\n"
        r"\end{document}" "\n"
    )

    output_path.write_text(tex)
    print(f"Written: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Collecting IPC data from {SENS_DIR} …")
    data = collect_all()

    print("\nNormalized harmonic mean IPC summary (relative to baseline, 100% = baseline):")
    print(f"{'bmax':>5}  {'dt':>4}  {'norm_hm_ipc (%)':>16}")
    print("-" * 31)
    for bmax in BROADCAST_MAX_VALUES:
        for dt in DEPENDENTS_THRESHOLD_VALUES:
            hm = data.get((bmax, dt))
            val = f"{hm:.2f}%" if hm is not None else "N/A"
            print(f"{bmax:>5}  {dt:>4}  {val:>16}")

    generate_tex(data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
