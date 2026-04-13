#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) grouped bar chart showing the
reduction in wakeup tag comparisons (in %) of sereno/sqbcast and sereno/stale
relative to the sereno/ckpt baseline.

Per-benchmark value: (1 - variant_rate / ckpt_rate) * 100
where rate = iqWakeupComparisons / committedInsts

The rightmost group shows the harmonic-mean ratio:
  HM_ratio = (1 - HM_variant / HM_baseline) * 100
where HM_* is the harmonic mean of the per-benchmark rate.

stat: system.cpu.iew.iqWakeupComparisons
      normalised by: system.cpu.commitStats0.numInsts

Variants compared
-----------------
  Baseline : runs/output/micro26/baseline/12B_-1P  (reference = 0 %)
  ckpt     : runs/output/micro26/sereno/ckpt
  sqbcast  : runs/output/micro26/sereno/sqbcast
  stale    : runs/output/micro26/sereno/stale

IPC per benchmark is computed as a weighted arithmetic mean over simpoints
(weights are embedded in the simpoint directory names and sum to 1).

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
    "ckpt":    ROOT / "runs/output/micro26/sereno/ckpt",
    "sqbcast": ROOT / "runs/output/micro26/sereno/sqbcast",
    "stale":   ROOT / "runs/output/micro26/sereno/stale",
}

OUTPUT_DIR = ROOT / "runs/output/micro26/graphs"
OUTPUT_TEX = OUTPUT_DIR / "comparisons_relative_sereno_variants.tex"

COMP_STAT  = "system.cpu.iew.iqWakeupComparisons"
INSTR_STAT = "system.cpu.commitStats0.numInsts"

# Set to a benchmark name (e.g. "628.pop2_s") for per-simpoint debug output.
DEBUG_BM: Optional[str] = "628.pop2_s"

# Colors and patterns — order matches APPROACHES above.
BAR_COLORS: list[tuple[str, int, int, int]] = [
    ("clrCkpt",    31, 119, 180),   # tableau blue
    ("clrSqbcast", 214,  39,  40),   # tableau red
    ("clrStale",    44, 160,  44),   # tableau green
]
# None = solid fill; otherwise a pgfplots pattern name.
BAR_PATTERNS: list[Optional[str]] = [
    None,                # ckpt
    "north east lines",  # sqbcast
    "crosshatch",        # stale
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


def parse_two_stats(stats_file: Path, stat_a: str, stat_b: str):
    """
    Return (value_a, value_b) from the final stats dump of a stats.txt file.
    Returns (None, None) on failure.
    """
    in_dump = False
    last_a: Optional[float] = None
    last_b: Optional[float] = None
    cur_a:  Optional[float] = None
    cur_b:  Optional[float] = None

    try:
        with open(stats_file, 'r', errors='replace') as f:
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
                if parts[0] == stat_a:
                    if len(parts) >= 2:
                        try:
                            cur_a = float(parts[1])
                        except ValueError:
                            pass
                elif parts[0] == stat_b:
                    if len(parts) >= 2:
                        try:
                            cur_b = float(parts[1])
                        except ValueError:
                            pass
    except OSError:
        return None, None

    return last_a, last_b

# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_comp_rate(base_dir: Path) -> dict[str, float]:
    """
    Walk *base_dir* and return {benchmark: weighted_comparisons_per_instr}.
    comparisons_per_instr = iqWakeupComparisons / committedInsts
    """
    stats_files = sorted(
        f for f in base_dir.glob("**/stats.txt")
        if "sensibility_analysis" not in f.parts
    )
    if not stats_files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}

    weighted_rate: dict[str, float] = defaultdict(float)
    weight_sum:    dict[str, float] = defaultdict(float)

    for sf in stats_files:
        comps, insts = parse_two_stats(sf, COMP_STAT, INSTR_STAT)
        if comps is None:
            print(f"  INFO: {COMP_STAT} not found in {sf}, defaulting to 0 (100% reduction)")
            comps = 0.0
        if insts is None or insts == 0:
            print(f"  WARNING: could not parse {INSTR_STAT} (or zero) from {sf}")
            continue
        rate      = comps / insts
        benchmark = extract_benchmark(sf)
        weight    = extract_weight(sf)

        if DEBUG_BM and benchmark == DEBUG_BM:
            simpoint = sf.parent.parent.name
            print(f"  [DEBUG {base_dir.name}] [{benchmark}]  simpoint={simpoint}  weight={weight:.6f}  insts={insts:.0f}")
            print(f"    comps={comps:.0f}  rate={rate:.8f}  w*rate={weight * rate:.8f}")

        weighted_rate[benchmark] += weight * rate
        weight_sum[benchmark]    += weight

    result: dict[str, float] = {}
    for bm in weighted_rate:
        w = weight_sum[bm]
        if w > 0:
            result[bm] = weighted_rate[bm] / w
            if DEBUG_BM and bm == DEBUG_BM:
                print(f"  [DEBUG {base_dir.name}] [{bm}]  FINAL  weight_sum={w:.6f}  weighted_mean={result[bm]:.8f}")
    return result


def harmonic_mean(values: list[float]) -> float:
    if not values:
        return float('nan')
    pos_recip_sum = sum(1.0 / v for v in values if v > 0)
    if pos_recip_sum == 0:
        return 0.0
    return len(values) / pos_recip_sum


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
    baseline_rates: dict[str, float],
    approach_data: dict[str, dict[str, float]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_benchmarks: list[str] = sorted(
        {bm for data in approach_data.values() for bm in data}
        & set(baseline_rates)
    )
    x_labels = all_benchmarks + ["WeightedMean"]
    approach_names = list(approach_data.keys())

    baseline_vals_all = [baseline_rates[bm] for bm in all_benchmarks if bm in baseline_rates]
    total_baseline = sum(baseline_vals_all)

    pct_data: dict[str, dict[str, float]] = {}
    ews_pct:  dict[str, float] = {}
    for name, d in approach_data.items():
        pct: dict[str, float] = {}
        weighted_pct_sum = 0.0
        weight_sum_inner = 0.0
        for bm in all_benchmarks:
            base = baseline_rates.get(bm)
            val  = d.get(bm)
            if base is not None and val is not None and base > 0:
                pct[bm] = (1.0 - val / base) * 100.0
                weighted_pct_sum += base * pct[bm]
                weight_sum_inner += base
        pct_data[name] = pct
        ews_pct[name] = weighted_pct_sum / weight_sum_inner if weight_sum_inner > 0 else float('nan')

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
        r"    ybar            = 0.5pt," "\n"
        r"    area legend," "\n"
        r"    bar width       = 4pt," "\n"
        r"    width           = 15.5cm," "\n"
        r"    height          = 6cm," "\n"
        r"    enlarge x limits= 0.03," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    x tick label style = {rotate=90, anchor=east, font=\normalsize}," "\n"
        r"    ymin            = 0," "\n"
        r"    ymax            = 100," "\n"
        r"    ytick           = {0, 20, 40, 60, 80, 100}," "\n"
        r"    extra y ticks   = {0}," "\n"
        r"    extra y tick style = {" "\n"
        r"        grid=major," "\n"
        r"        grid style={solid, black!50, line width=0.6pt}," "\n"
        r"    }," "\n"
        r"    ylabel          = {Comparisons reduction}," "\n"
        r"    ylabel style    = {font=\normalsize}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    legend style    = {" "\n"
        r"        at={(0.5,1.03)}, anchor=south," "\n"
        r"        font=\normalsize," "\n"
        r"        cells={anchor=west}," "\n"
        r"        draw=gray!50," "\n"
        r"        fill=white," "\n"
        r"        /tikz/every even column/.append style={column sep=10pt}," "\n"
        r"    }," "\n"
        r"    legend columns  = -1," "\n"
        r"    tick label style= {font=\normalsize}," "\n"
        r"    yticklabel        = {\pgfmathprintnumber\tick\%}," "\n"
        r"    after end axis/.code={" "\n"
        r"        \begin{pgfonlayer}{background}" "\n"
        r"            \fill[gray!15] ([xshift=-10pt]{axis cs:WeightedMean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
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
    print(f"Collecting comparison rates for {BASELINE_KEY} …")
    baseline_rates = collect_comp_rate(BASELINE_DIR)
    print(f"  → {len(baseline_rates)} benchmarks found")

    approach_data: dict[str, dict[str, float]] = {}
    for name, base_dir in APPROACHES.items():
        if not base_dir.exists():
            print(f"SKIP {name}: directory not found ({base_dir})")
            continue
        print(f"Collecting comparison rates for {name} …")
        data = collect_comp_rate(base_dir)
        print(f"  → {len(data)} benchmarks found")
        approach_data[name] = data

    if not approach_data:
        print("No data found – nothing to plot.")
        return

    all_bms = sorted(
        {bm for d in approach_data.values() for bm in d} & set(baseline_rates)
    )

    # Print summary table.
    header = f"{'Benchmark':<25}" + "".join(f"{n:>14}" for n in approach_data)
    print("\n" + header)
    print("-" * len(header))
    opt_rate_lists: dict[str, list[float]] = {n: [] for n in approach_data}
    for bm in all_bms:
        row = f"{bm:<25}"
        base = baseline_rates.get(bm, float('nan'))
        for name, d in approach_data.items():
            v = d.get(bm, float('nan'))
            pct = (1.0 - v / base) * 100.0 if base and base > 0 and v == v else float('nan')
            row += f"{pct:>13.2f}%"
            if v == v:
                opt_rate_lists[name].append(v)
        print(row)

    wm_row = f"{'Weighted Mean':<25}"
    for name, d in approach_data.items():
        numerator = 0.0
        denominator = 0.0
        for bm in all_bms:
            base = baseline_rates.get(bm)
            val = d.get(bm)
            if base is not None and val is not None and base > 0:
                pct = (1.0 - val / base) * 100.0
                numerator += base * pct
                denominator += base
        wm_pct = numerator / denominator if denominator > 0 else float('nan')
        wm_row += f"{wm_pct:>13.2f}%"
    print("-" * len(header))
    print(wm_row)

    generate_tikz(baseline_rates, approach_data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
