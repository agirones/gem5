#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) grouped bar chart showing the
reduction in wakeup tag comparisons (in %) of each non-baseline approach
relative to the baseline.

Per-benchmark value: (1 - approach_comps / baseline_comps) * 100
where comps = weighted mean of raw iqWakeupComparisons across simpoints
(weight = simpoint weight).

The rightmost bar shows the weighted arithmetic mean across benchmarks,
weighted by baseline_comps[bm] / sum(baseline_comps).

stat: system.cpu.iew.iqWakeupComparisons
      (counts IQ tag comparisons on the broadcast path only)

Approaches
----------
  Baseline  : runs/output/micro26/baseline/12B_-1P  (reference = 0 %)
  Sereno    : runs/output/micro26/sereno/ckpt
  EDF-DMT/2 : runs/output/micro26/edf/dmt_slots/2
  2-Use/2   : runs/output/micro26/n-use/ino-i-buffer/i-buffer-head/2

Output: a standalone .tex file importable with \\input{} in an Overleaf
document that uses the 'standalone' package.
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path("/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU")

BASELINE_KEY = "Baseline"
BASELINE_DIR = ROOT / "runs/output/micro26/baseline/12B_-1P"

APPROACHES: dict[str, Path] = {
    "Sereno":    ROOT / "runs/output/micro26/sereno/ckpt",
    "Hybrid-WL": ROOT / "runs/output/micro26/hybrid-wl/ckpt",
    "N-Use":     ROOT / "runs/output/micro26/n-use/ino-i-buffer/i-buffer-head/2",
    "EDF":       ROOT / "runs/output/micro26/edf/dmt_slots/2",
}

OUTPUT_DIR = ROOT / "runs/output/micro26/graphs"
OUTPUT_TEX = OUTPUT_DIR / "comparisons_relative.tex"

COMP_STAT  = "system.cpu.iew.iqWakeupComparisons"

# Colors and patterns match ipc_relative.tex exactly — order matches APPROACHES.
BAR_COLORS: list[tuple[str, int, int, int]] = [
    ("clrSereno",  31, 119, 180),
    ("clrHybridWL",  214,  39,  40),
    ("clrNUse",    44, 160,  44),
    ("clrEDF",    255, 127,  14),
]
# None = solid fill; otherwise a pgfplots pattern name.
BAR_PATTERNS: list[Optional[str]] = [
    None,                    # Sereno      — solid
    "north east lines",      # Hybrid-WL
    "crosshatch",            # N-Use
    "north west lines",      # EDF
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
    Expected layout: {base_dir}/width8/{benchmark}/{simpoint_dir}/m5out/stats.txt
    """
    return stats_file.parent.parent.parent.name


def parse_stat(stats_file: Path, stat: str) -> Optional[float]:
    """
    Return the value of *stat* from the final stats dump of a stats.txt file.
    Returns None on failure.
    """
    in_dump = False
    last:    Optional[float] = None
    cur:     Optional[float] = None

    try:
        with open(stats_file, 'r', errors='replace') as f:
            for line in f:
                if '---------- Begin Simulation Statistics ----------' in line:
                    in_dump = True
                    cur = None
                    continue
                if '---------- End Simulation Statistics   ----------' in line:
                    if cur is not None:
                        last = cur
                    in_dump = False
                    continue
                if not in_dump:
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[0] == stat:
                    try:
                        cur = float(parts[1])
                    except ValueError:
                        pass
    except OSError:
        return None

    return last

# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_comp_rate(base_dir: Path) -> dict[str, float]:
    """
    Walk *base_dir* and return {benchmark: weighted_mean_raw_comparisons}
    where the weighted mean is sum(weight_i * comps_i) / sum(weight_i)
    over all simpoints for each benchmark.
    """
    stats_files = sorted(
        f for f in base_dir.glob("**/stats.txt")
        if "sensibility_analysis" not in f.parts
    )
    if not stats_files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}

    weighted_comps: dict[str, float] = defaultdict(float)
    weight_sum:     dict[str, float] = defaultdict(float)

    for sf in stats_files:
        comps = parse_stat(sf, COMP_STAT)
        if comps is None:
            print(f"  INFO: {COMP_STAT} not found in {sf}, defaulting to 0 (100% reduction)")
            comps = 0.0
        benchmark = extract_benchmark(sf)
        weight    = extract_weight(sf)
        weighted_comps[benchmark] += weight * comps
        weight_sum[benchmark]     += weight

    return {
        bm: weighted_comps[bm] / weight_sum[bm]
        for bm in weighted_comps
        if weight_sum[bm] > 0
    }


def clean_label(benchmark: str) -> str:
    """Strip leading SPEC number+dot and trailing '_s'. E.g. '600.perlbench_s' -> 'perlbench'."""
    label = re.sub(r'^\d+\.', '', benchmark)
    label = re.sub(r'_s$', '', label)
    return label

# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------

def _escape_latex(s: str) -> str:
    return s.replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')


def generate_tikz(
    baseline_comps: dict[str, float],
    approach_data: dict[str, dict[str, float]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_benchmarks: list[str] = sorted(
        {bm for data in approach_data.values() for bm in data}
        & set(baseline_comps)
    )
    x_labels = all_benchmarks + ["WeightedMean"]
    approach_names = list(approach_data.keys())

    grand_total_comps = sum(baseline_comps.get(bm, 0.0) for bm in all_benchmarks)
    bm_weights = (
        {bm: baseline_comps.get(bm, 0.0) / grand_total_comps for bm in all_benchmarks}
        if grand_total_comps > 0
        else {bm: 1.0 / len(all_benchmarks) for bm in all_benchmarks}
    )

    pct_data: dict[str, dict[str, float]] = {}
    ews_pct:  dict[str, float] = {}
    for name, d in approach_data.items():
        pct: dict[str, float] = {}
        for bm in all_benchmarks:
            base = baseline_comps.get(bm)
            val  = d.get(bm)
            if base is not None and val is not None and base > 0:
                pct[bm] = (1.0 - val / base) * 100.0
        pct_data[name] = pct
        present   = [bm for bm in all_benchmarks if bm in pct]
        tot_w     = sum(bm_weights[bm] for bm in present)
        ews_pct[name] = (
            sum(bm_weights[bm] * pct[bm] for bm in present) / tot_w
            if tot_w > 0 else float('nan')
        )

    coords: dict[str, list[str]] = {}
    for name in approach_names:
        pct = pct_data[name]
        vals_bm = [pct.get(bm, float('nan')) for bm in all_benchmarks]
        vals = vals_bm + [ews_pct[name]]
        coord_strs = [
            f"({label}, {v:.6f})"
            for label, v in zip(x_labels, vals)
            if v == v  # skip NaN
        ]
        coords[name] = coord_strs

    sym_coords = ", ".join(x_labels)
    display_labels = [clean_label(lb) for lb in all_benchmarks] + [r"\textbf{Mean}"]
    xticklabels = ", ".join(display_labels)

    define_colors = ""
    for cname, r, g, b in BAR_COLORS:
        define_colors += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    addplot_lines = []
    for i, name in enumerate(approach_names):
        cname   = BAR_COLORS[i % len(BAR_COLORS)][0]
        pattern = BAR_PATTERNS[i % len(BAR_PATTERNS)]
        escaped_name = _escape_latex(name)
        coord_body = "\n        ".join(coords[name])
        pattern_line = (
            f"        postaction={{pattern={pattern}, draw=black}},\n"
            if pattern else ""
        )
        addplot_lines.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw={cname}!60!black,\n"
            f"        line width=0.4pt,\n"
            + pattern_line +
            f"    ] coordinates {{\n"
            f"        {coord_body}\n"
            f"    }};\n"
            f"    \\addlegendentry{{{escaped_name}}}"
        )

    addplot_str = "\n\n".join(addplot_lines)

    tex = (
        r"\documentclass[tikz]{standalone}" "\n"
        r"\usepackage{pgfplots}" "\n"
        r"\usetikzlibrary{patterns}" "\n"
        r"\pgfplotsset{compat=1.18}" "\n"
        "\n"
        r"\pgfdeclarelayer{background}" "\n"
        r"\pgfsetlayers{background,main}" "\n"
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
        r"    width           = 1.3\textwidth, height=4cm, scale only axis," "\n"
        r"    ybar            = 0.5pt," "\n"
        r"    area legend," "\n"
        r"    bar width       = 3.5pt," "\n"
        r"    enlarge x limits= 0.03," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    x tick label style = {rotate=90, anchor=east}," "\n"
        r"    ymin            =   0," "\n"
        r"    ymax            = 100," "\n"
        r"    ytick           = {0, 20, 40, 60, 80, 100}," "\n"
        r"    ylabel          = {Comparisons reduction}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    legend style    = {" "\n"
        r"        at={(0.5,1.03)}, anchor=south," "\n"
        r"        font=\scriptsize," "\n"
        r"        cells={anchor=west}," "\n"
        r"        draw=none," "\n"
        r"        /tikz/every even column/.append style={column sep=10pt}," "\n"
        r"    }," "\n"
        r"    legend columns  = -1," "\n"
        r"    tick label style= {font=\scriptsize}," "\n"
        r"    yticklabel        = {\pgfmathprintnumber\tick\%}," "\n"
        r"    after end axis/.code={" "\n"
        r"        \begin{pgfonlayer}{background}" "\n"
        r"        \fill[gray!60] ([xshift=-11pt]{axis cs:WeightedMean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
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
    if not BASELINE_DIR.exists():
        print(f"ERROR: baseline directory not found: {BASELINE_DIR}")
        return
    print(f"Collecting comparison stats for {BASELINE_KEY} …")
    baseline_comps = collect_comp_rate(BASELINE_DIR)
    print(f"  → {len(baseline_comps)} benchmarks found")

    approach_data: dict[str, dict[str, float]] = {}
    for name, base_dir in APPROACHES.items():
        if not base_dir.exists():
            print(f"SKIP {name}: directory not found ({base_dir})")
            continue
        print(f"Collecting comparison stats for {name} …")
        data = collect_comp_rate(base_dir)
        print(f"  → {len(data)} benchmarks found")
        approach_data[name] = data

    if not approach_data:
        print("No data found – nothing to plot.")
        return

    all_bms = sorted(
        {bm for d in approach_data.values() for bm in d} & set(baseline_comps)
    )

    # Print summary table
    header = f"{'Benchmark':<25}" + "".join(f"{n:>14}" for n in approach_data)
    print("\n" + header)
    print("-" * len(header))
    for bm in all_bms:
        row  = f"{bm:<25}"
        base = baseline_comps.get(bm, float('nan'))
        for name, d in approach_data.items():
            v   = d.get(bm, float('nan'))
            pct = (1.0 - v / base) * 100.0 if base > 0 and v == v else float('nan')
            row += f"{pct:>13.2f}%"
        print(row)

    grand_total_comps_m = sum(baseline_comps.get(bm, 0.0) for bm in all_bms)
    bm_weights_m = (
        {bm: baseline_comps.get(bm, 0.0) / grand_total_comps_m for bm in all_bms}
        if grand_total_comps_m > 0
        else {bm: 1.0 / len(all_bms) for bm in all_bms}
    )
    wm_row = f"{'Weighted Mean':<25}"
    for name, d in approach_data.items():
        present_m = [bm for bm in all_bms if bm in baseline_comps and bm in d and baseline_comps[bm] > 0]
        tot_w_m   = sum(bm_weights_m[bm] for bm in present_m)
        wm_pct    = (
            sum(bm_weights_m[bm] * (1.0 - d[bm] / baseline_comps[bm]) * 100.0 for bm in present_m) / tot_w_m
            if tot_w_m > 0 else float('nan')
        )
        wm_row += f"{wm_pct:>13.2f}%"
    print("-" * len(header))
    print(wm_row)

    generate_tikz(baseline_comps, approach_data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
