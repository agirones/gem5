#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) grouped bar chart showing the
reduction in wakeup tag comparisons (in %) of Sereno, Sereno-SQ, and Hybrid-WL
relative to the baseline.

Per-benchmark value: (1 - approach_rate / baseline_rate) * 100
where:
  baseline_rate  = iqWakeupComparisons / numInsts
  Sereno rate    = iqWakeupComparisons / numInsts
  Sereno-SQ rate = iqWakeupComparisons / numInsts
  Hybrid-WL rate = (iqWakeupComparisons + unnecessaryWakeupComparisons) / numInsts

The rightmost column shows the harmonic-mean ratio across benchmarks.

Output: runs/output/micro26/graphs/comparisons_breakdown.tex
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
    "Sereno":    ROOT / "runs/output/micro26/sereno/ckpt",
    "Sereno-SQ": ROOT / "runs/output/micro26/sereno/sqbcast",
    "Hybrid-WL": ROOT / "runs/output/micro26/hybrid-wl/12B_2P",
}

OUTPUT_DIR = ROOT / "runs/output/micro26/graphs"
OUTPUT_TEX = OUTPUT_DIR / "comparisons_breakdown.tex"

INSTR_STAT = "system.cpu.commitStats0.numInsts"
IQ_COMP    = "system.cpu.iew.iqWakeupComparisons"
UNNEC_COMP = "system.cpu.iew.unnecessaryWakeupComparisons"

# Stats to parse per approach (and baseline).
APPROACH_STATS: dict[str, list[str]] = {
    "Baseline":  [IQ_COMP, INSTR_STAT],
    "Sereno":    [IQ_COMP, INSTR_STAT],
    "Sereno-SQ": [IQ_COMP, INSTR_STAT],
    "Hybrid-WL": [IQ_COMP, UNNEC_COMP, INSTR_STAT],
}

# Colors (latex-name, R, G, B) and patterns — one per approach.
BAR_COLORS: list[tuple[str, int, int, int]] = [
    ("clrSereno",    31, 119, 180),   # tableau blue
    ("clrSerenoSQ", 114, 158, 206),   # light blue
    ("clrHybridWL", 214,  39,  40),   # tableau red
]
BAR_PATTERNS: list[Optional[str]] = [
    None,               # Sereno      — solid
    "dots",             # Sereno-SQ
    "north east lines", # Hybrid-WL
]

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def extract_weight(path: Path) -> float:
    m = re.search(r'weight_([0-9]+\.[0-9]+)', str(path))
    return float(m.group(1)) if m else 1.0


def extract_benchmark(stats_file: Path) -> str:
    return stats_file.parent.parent.parent.name


def parse_stats(stats_file: Path, stat_names: list[str]) -> Optional[dict[str, float]]:
    targets = set(stat_names)
    in_dump = False
    cur: dict[str, float] = {}
    last: dict[str, float] = {}

    try:
        with open(stats_file, 'r', errors='replace') as f:
            for line in f:
                if '---------- Begin Simulation Statistics ----------' in line:
                    in_dump = True
                    cur = {}
                    continue
                if '---------- End Simulation Statistics   ----------' in line:
                    if cur:
                        last = dict(cur)
                    in_dump = False
                    continue
                if not in_dump:
                    continue
                parts = line.split()
                if parts and parts[0] in targets:
                    if len(parts) >= 2:
                        try:
                            cur[parts[0]] = float(parts[1])
                        except ValueError:
                            pass
    except OSError:
        return None

    return last if last else None


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_comp_rate(
    base_dir: Path,
    stat_names: list[str],
    rate_fn,   # callable({stat_name: value}) -> float | None
) -> dict[str, float]:
    """
    Walk *base_dir*, parse *stat_names* from each stats.txt, apply *rate_fn*
    to get a per-simpoint rate, and return {benchmark: weighted_rate}.
    """
    stats_files = sorted(
        f for f in base_dir.glob("**/stats.txt")
        if "sensibility_analysis" not in f.parts
    )
    if not stats_files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}

    weighted_rate: dict[str, float] = defaultdict(float)
    weight_sum:   dict[str, float]  = defaultdict(float)

    for sf in stats_files:
        vals = parse_stats(sf, stat_names)
        if vals is None:
            print(f"  WARNING: I/O error reading {sf}")
            continue
        rate = rate_fn(vals)
        if rate is None:
            continue
        bm     = extract_benchmark(sf)
        weight = extract_weight(sf)
        weighted_rate[bm] += weight * rate
        weight_sum[bm]    += weight

    return {bm: weighted_rate[bm] / weight_sum[bm]
            for bm in weighted_rate if weight_sum[bm] > 0}


# Rate functions — map {stat_name: value} → comparisons/instr (or None).

def _rate_baseline(vals):
    comps = vals.get(IQ_COMP)
    insts = vals.get(INSTR_STAT)
    if comps is None or not insts:
        return None
    return comps / insts

def _rate_sereno(vals):
    return _rate_baseline(vals)

def _rate_serenosq(vals):
    return _rate_baseline(vals)

def _rate_hybridwl(vals):
    iq    = vals.get(IQ_COMP)
    unnec = vals.get(UNNEC_COMP)
    insts = vals.get(INSTR_STAT)
    if iq is None or unnec is None or not insts:
        return None
    return (iq + unnec) / insts


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def harmonic_mean(values: list[float]) -> float:
    pos = [v for v in values if v > 0]
    if not pos:
        return float('nan')
    return len(pos) / sum(1.0 / v for v in pos)


def clean_label(benchmark: str) -> str:
    label = re.sub(r'^\d+\.', '', benchmark)
    label = re.sub(r'_s$', '', label)
    return label


def _escape_latex(s: str) -> str:
    return s.replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')


# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------

def generate_tikz(
    baseline_rates: dict[str, float],
    approach_data: dict[str, dict[str, float]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    approach_names = list(approach_data.keys())
    all_benchmarks: list[str] = sorted(
        {bm for data in approach_data.values() for bm in data}
        & set(baseline_rates)
    )

    hm_baseline = harmonic_mean(
        [baseline_rates[bm] for bm in all_benchmarks if bm in baseline_rates]
    )

    # Compute % reduction per benchmark and HM column.
    pct_data: dict[str, dict[str, float]] = {}
    hm_pct:   dict[str, float] = {}
    for name, d in approach_data.items():
        pct: dict[str, float] = {}
        opt_vals: list[float] = []
        for bm in all_benchmarks:
            base = baseline_rates.get(bm)
            val  = d.get(bm)
            if base and base > 0 and val is not None:
                pct[bm] = (1.0 - val / base) * 100.0
                opt_vals.append(val)
        pct_data[name] = pct
        hm_opt = harmonic_mean(opt_vals)
        hm_pct[name] = (
            (1.0 - hm_opt / hm_baseline) * 100.0
            if hm_baseline > 0 else float('nan')
        )

    x_labels = all_benchmarks + ["HarmonicMean"]
    sym_coords     = ", ".join(x_labels)
    display_labels = [clean_label(b) for b in all_benchmarks] + [r"\textbf{Harmonic Mean}"]
    xticklabels    = ", ".join(display_labels)

    define_colors = ""
    for cname, r, g, b in BAR_COLORS:
        define_colors += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    addplot_lines: list[str] = []
    for i, name in enumerate(approach_names):
        cname   = BAR_COLORS[i % len(BAR_COLORS)][0]
        pattern = BAR_PATTERNS[i % len(BAR_PATTERNS)]
        pct     = pct_data[name]

        coord_strs: list[str] = []
        for bm in all_benchmarks:
            v = pct.get(bm)
            if v is not None:
                coord_strs.append(f"({bm}, {v:.6f})")
        if hm_pct[name] == hm_pct[name]:   # skip NaN
            coord_strs.append(f"(HarmonicMean, {hm_pct[name]:.6f})")

        coord_body   = "\n        ".join(coord_strs)
        pattern_line = (
            f"        postaction={{pattern={pattern}, draw=black}},\n"
            if pattern else ""
        )
        escaped_name = _escape_latex(name)

        addplot_lines.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw={cname}!70!black,\n"
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
        r"        \draw[#1, draw=black!60, line width=0.3pt]" "\n"
        r"            (0pt,-1pt) rectangle (5pt,4pt);" "\n"
        r"    }," "\n"
        r"}" "\n"
        "\n"
        r"\begin{document}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"\begin{axis}[" "\n"
        r"    area legend," "\n"
        r"    ybar            = 0.5pt," "\n"
        r"    bar width       = 4pt," "\n"
        r"    width           = 15.5cm," "\n"
        r"    height          = 6cm," "\n"
        r"    enlarge x limits= 0.03," "\n"
        r"    clip            = false," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    x tick label style = {rotate=90, anchor=east, font=\scriptsize}," "\n"
        r"    ymin            = 0," "\n"
        r"    ymax            = 100," "\n"
        r"    ytick           = {0, 20, 40, 60, 80, 100}," "\n"
        r"    ylabel          = {Comparisons reduction}," "\n"
        r"    ylabel style    = {font=\small}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    yticklabel      = {\pgfmathprintnumber\tick\%}," "\n"
        r"    legend style    = {" "\n"
        r"        at={(0.5,1.03)}, anchor=south," "\n"
        r"        font=\scriptsize," "\n"
        r"        cells={anchor=west}," "\n"
        r"        draw=gray!50," "\n"
        r"        fill=white," "\n"
        r"        /tikz/every even column/.append style={column sep=10pt}," "\n"
        r"    }," "\n"
        r"    legend columns  = -1," "\n"
        r"    tick label style= {font=\scriptsize}," "\n"
        r"    after end axis/.code={" "\n"
        r"        \begin{pgfonlayer}{background}" "\n"
        r"            \fill[gray!15] ([xshift=-6pt]{axis cs:HarmonicMean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
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
    configs = {
        "Baseline":  (BASELINE_DIR,            APPROACH_STATS["Baseline"],  _rate_baseline),
        "Sereno":    (APPROACHES["Sereno"],     APPROACH_STATS["Sereno"],    _rate_sereno),
        "Sereno-SQ": (APPROACHES["Sereno-SQ"], APPROACH_STATS["Sereno-SQ"], _rate_serenosq),
        "Hybrid-WL": (APPROACHES["Hybrid-WL"], APPROACH_STATS["Hybrid-WL"], _rate_hybridwl),
    }

    all_rates: dict[str, dict[str, float]] = {}
    for name, (base_dir, stats, rate_fn) in configs.items():
        if not base_dir.exists():
            print(f"SKIP {name}: directory not found ({base_dir})")
            continue
        print(f"Collecting comparison rates for {name} …")
        data = collect_comp_rate(base_dir, stats, rate_fn)
        print(f"  → {len(data)} benchmarks")
        all_rates[name] = data

    baseline_rates = all_rates.get("Baseline", {})
    if not baseline_rates:
        print("ERROR: no baseline data.")
        return

    approach_data = {k: v for k, v in all_rates.items() if k != "Baseline"}
    if not approach_data:
        print("No approach data – nothing to plot.")
        return

    # Summary table.
    all_bms = sorted(
        {bm for d in approach_data.values() for bm in d} & set(baseline_rates)
    )
    header = f"{'Benchmark':<25}" + "".join(f"{n:>16}" for n in approach_data)
    print("\n" + header)
    print("-" * len(header))
    opt_rate_lists: dict[str, list[float]] = {n: [] for n in approach_data}
    for bm in all_bms:
        base = baseline_rates.get(bm, float('nan'))
        row  = f"{bm:<25}"
        for name, d in approach_data.items():
            v   = d.get(bm, float('nan'))
            pct = (1.0 - v / base) * 100.0 if base > 0 and v == v else float('nan')
            row += f"{pct:>15.2f}%"
            if v == v:
                opt_rate_lists[name].append(v)
        print(row)

    hm_baseline = harmonic_mean(
        [baseline_rates[bm] for bm in all_bms if bm in baseline_rates]
    )
    hm_row = f"{'Harmonic Mean':<25}"
    for name in approach_data:
        hm_opt = harmonic_mean(opt_rate_lists[name])
        hm_pct = (1.0 - hm_opt / hm_baseline) * 100.0 if hm_baseline > 0 else float('nan')
        hm_row += f"{hm_pct:>15.2f}%"
    print("-" * len(header))
    print(hm_row)

    generate_tikz(baseline_rates, approach_data, OUTPUT_TEX)


if __name__ == "__main__":
    main()

