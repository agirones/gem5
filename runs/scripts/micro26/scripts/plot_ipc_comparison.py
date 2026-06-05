#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) grouped bar chart comparing IPC
across approaches for each SPEC benchmark, with the harmonic mean as the
rightmost group.

Approaches
----------
  Baseline  : runs/output/micro26/baseline/12B_-1P
  Sereno    : runs/output/micro26/sereno/ckpt
  EDF-DMT/2 : runs/output/micro26/edf/dmt_slots/2
  2-Use/2   : runs/output/micro26/n-use/ino-i-buffer/i-buffer-head/2

IPC per benchmark is computed as a weighted sum over simpoints:
    IPC = sum(weight * simInsts) / sum(weight * numCycles)
(weights are embedded in the simpoint directory names and sum to 1).
simInsts and system.cpu.numCycles are taken from the final stats dump.
The rightmost "HMean" bar shows the harmonic mean of per-benchmark IPCs.

Output: a standalone .tex file importable with \input{} in an Overleaf document
that uses the 'standalone' package.
"""

import re
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path("/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU")

APPROACHES: dict[str, Path] = {
    "Baseline":  ROOT / "runs/output/micro26/baseline/12B_-1P",
    "Sereno":    ROOT / "runs/output/micro26/sereno/ckpt",
    "2-Use/2":   ROOT / "runs/output/micro26/n-use/ino-i-buffer/i-buffer-head/2",
    "EDF-DMT/2": ROOT / "runs/output/micro26/edf/dmt_slots/2",
}

OUTPUT_DIR = ROOT / "runs/output/micro26/graphs"
OUTPUT_TEX = OUTPUT_DIR / "ipc_comparison.tex"

INSTS_STAT = "simInsts"
CYCLES_STAT = "system.cpu.numCycles"

# Tableau-10 inspired palette: (color name, R, G, B)
# Order must match APPROACHES: Baseline, Sereno, 2-Use/2, EDF-DMT/2
BAR_COLORS: list[tuple[str, int, int, int]] = [
    ("clrBaseline",  130, 130, 130),   # neutral gray
    ("clrSereno",     31, 119, 180),   # tableau blue
    ("clrNUse",       44, 160,  44),   # tableau green
    ("clrEDF",       255, 127,  14),   # tableau orange
]

# ---------------------------------------------------------------------------
# Parsing helpers
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



def parse_stats(stats_file: Path):
    """
    Return (simInsts, numCycles) from the final stats dump.
    """
    in_dump = False
    last: tuple[float, float] | None = None
    current_insts: float | None = None
    current_cycles: float | None = None

    try:
        with open(stats_file, 'r', errors='replace') as f:
            for line in f:
                if '---------- Begin Simulation Statistics ----------' in line:
                    in_dump = True
                    current_insts = current_cycles = None
                    continue
                if '---------- End Simulation Statistics   ----------' in line:
                    if current_insts is not None and current_cycles is not None:
                        last = (current_insts, current_cycles)
                    in_dump = False
                    continue
                if not in_dump:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                if parts[0] == INSTS_STAT:
                    try:
                        current_insts = float(parts[1])
                    except ValueError:
                        pass
                elif parts[0] == CYCLES_STAT:
                    try:
                        current_cycles = float(parts[1])
                    except ValueError:
                        pass
    except OSError:
        return None

    return last

# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_ipc(base_dir: Path) -> dict[str, float]:
    """
    Walk *base_dir* and return {benchmark: weighted_IPC}.

    Per-benchmark IPC = sum(weight * simInsts) / sum(weight * numCycles).
    """
    stats_files = sorted(
        f for f in base_dir.glob("**/stats.txt")
        if "sensibility_analysis" not in f.parts
    )
    if not stats_files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}

    weighted_insts:  dict[str, float] = defaultdict(float)
    weighted_cycles: dict[str, float] = defaultdict(float)

    for sf in stats_files:
        parsed = parse_stats(sf)
        if parsed is None:
            print(f"  WARNING: could not parse stats from {sf}")
            continue
        insts, cycles = parsed
        if cycles == 0:
            print(f"  WARNING: zero cycles in {sf}, skipping")
            continue
        benchmark = extract_benchmark(sf)
        weight    = extract_weight(sf)
        weighted_insts[benchmark]  += weight * insts
        weighted_cycles[benchmark] += weight * cycles

    return {
        bm: weighted_insts[bm] / weighted_cycles[bm]
        for bm in weighted_insts
        if weighted_cycles[bm] > 0
    }


def harmonic_mean(values: list[float]) -> float:
    if not values:
        return float('nan')
    return len(values) / sum(1.0 / v for v in values if v > 0)

# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------

def _escape_latex(s: str) -> str:
    """Escape characters that are special in LaTeX tick labels."""
    return s.replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')


def generate_tikz(
    approach_data: dict[str, dict[str, float]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_benchmarks: list[str] = sorted(
        {bm for data in approach_data.values() for bm in data}
    )
    x_labels = all_benchmarks + ["HMean"]
    approach_names = list(approach_data.keys())
    n_approaches = len(approach_names)

    # Build per-approach coordinate lists (one entry per x_label).
    coords: dict[str, list[str]] = {}
    for name in approach_names:
        d = approach_data[name]
        vals_bm = [d.get(bm, float('nan')) for bm in all_benchmarks]
        hmean = harmonic_mean([v for v in vals_bm if not (v != v)])  # skip NaN
        vals = vals_bm + [hmean]
        coord_strs = [f"({label}, {v:.6f})" for label, v in zip(x_labels, vals)
                      if v == v]  # skip NaN
        coords[name] = coord_strs

    # symbolic x coords — pgfplots requires exact same strings used in \addplot
    sym_coords = ", ".join(x_labels)

    # Escaped x tick labels (rotate 45°)
    xticklabels = ", ".join(
        [_escape_latex(lb) for lb in x_labels[:-1]] + [r"\textbf{HMean}"]
    )

    # \definecolor lines for all approaches
    define_colors = ""
    for cname, r, g, b in BAR_COLORS:
        define_colors += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    # Build \addplot blocks — one per approach
    addplot_lines = []
    for i, name in enumerate(approach_names):
        cname = BAR_COLORS[i % len(BAR_COLORS)][0]
        escaped_name = _escape_latex(name)
        coord_body = "\n        ".join(coords[name])
        addplot_lines.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw={cname}!60!black,\n"
            f"        line width=0.4pt,\n"
            f"    ] coordinates {{\n"
            f"        {coord_body}\n"
            f"    }};\n"
            f"    \\addlegendentry{{{escaped_name}}}"
        )

    addplot_str = "\n\n".join(addplot_lines)

    tex = (
        r"\documentclass[tikz]{standalone}" "\n"
        r"\usepackage{pgfplots}" "\n"
        r"\pgfplotsset{compat=1.18}" "\n"
        "\n"
        r"\pgfdeclarelayer{background}" "\n"
        r"\pgfsetlayers{background,main}" "\n"
        "\n"
        + define_colors +
        "\n"
        # Single filled-rectangle legend icon per approach.
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
        r"    ybar            = 0.5pt," "\n"
        r"    area legend," "\n"
        r"    bar width       = 4pt," "\n"
        r"    width           = 16cm," "\n"
        r"    height          = 6cm," "\n"
        r"    enlarge x limits= 0.03," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    x tick label style = {rotate=45, anchor=east, font=\scriptsize}," "\n"
        r"    ymin            = 0," "\n"
        r"    ylabel          = {IPC}," "\n"
        r"    ylabel style    = {font=\small}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    legend style    = {" "\n"
        r"        at={(1.01,1)}, anchor=north west," "\n"
        r"        font=\scriptsize," "\n"
        r"        cells={anchor=west}," "\n"
        r"        draw=gray!50," "\n"
        r"        fill=white," "\n"
        r"        row sep=1pt," "\n"
        r"    }," "\n"
        r"    legend columns  = 1," "\n"
        r"    tick label style= {font=\scriptsize}," "\n"
        r"    after end axis/.code={" "\n"
        r"        \begin{pgfonlayer}{background}" "\n"
        r"            \fill[gray!30] ([xshift=-10.2pt]{axis cs:HMean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
        r"        \end{pgfonlayer}" "\n"
        r"    }," "\n"
        r"]" "\n"
        "\n"
        + addplot_str + "\n"
        "\n"
        r"\end{axis}" "\n"
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

    generate_tikz(approach_data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
