#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) grouped bar chart showing the
IPC change (in %) of each non-baseline approach relative to the baseline.
Negative values represent performance degradation.

Rebuttal configuration: L1 latency = 4, warmup = 10M (from checkpoint names).

Per-benchmark value: ((approach_IPC / baseline_IPC) - 1) * 100

The rightmost group shows the Equal-Work Speedup (EWS) as defined by
Eeckhout (2024): EWS = ((HM_optimized / HM_baseline) - 1) * 100
where HM_* is the harmonic mean of raw IPCs over all benchmarks.
Harmonic means are used exclusively — no arithmetic or geometric means.

Data sources (all under L1 latency 4):
  Baseline  : runs/output/micro26/rebuttal/cache_lat/baseline/4
  Sereno    : runs/output/micro26/rebuttal/cache_lat/sereno/4
  Hybrid-WL : runs/output/micro26/rebuttal/cache_lat/hybrid-wl/4
  N-Use     : runs/output/micro26/rebuttal/cache_lat/n-use/4
  EDF       : runs/output/micro26/rebuttal/cache_lat/edf/4

IPC per benchmark is computed as a weighted sum over simpoints:
    IPC = sum(weight * simInsts) / sum(weight * numCycles)
(weights are embedded in the simpoint directory names and sum to 1).
simInsts and system.cpu.numCycles are taken from the final stats dump.

Output: runs/output/micro26/rebuttal/ipc_relative/ipc_relative.tex
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[5]  # .../gem5-NTNU/

CACHE_LAT_DIR = ROOT / "runs/output/micro26/rebuttal/cache_lat"
L1_LATENCY = 4

BASELINE_KEY = "Baseline"
BASELINE_DIR = CACHE_LAT_DIR / "baseline" / str(L1_LATENCY)

APPROACHES: dict[str, Path] = {
    "Sereno":    CACHE_LAT_DIR / "sereno" / str(L1_LATENCY),
    "Hybrid-WL": CACHE_LAT_DIR / "hybrid-wl" / str(L1_LATENCY),
    "N-Use":     CACHE_LAT_DIR / "n-use" / str(L1_LATENCY),
    "EDF":       CACHE_LAT_DIR / "edf" / str(L1_LATENCY),
}

OUTPUT_DIR = ROOT / "runs/output/micro26/rebuttal/ipc_relative"
OUTPUT_TEX = OUTPUT_DIR / "ipc_relative.tex"

INSTS_STAT = "simInsts"
CYCLES_STAT = "system.cpu.numCycles"

BAR_COLORS: list[tuple[str, int, int, int]] = [
    ("clrSereno",   31, 119, 180),
    ("clrHybridWL", 214,  39,  40),
    ("clrNUse",     44, 160,  44),
    ("clrEDF",     255, 127,  14),
]

BAR_PATTERNS: list[Optional[str]] = [
    None,
    "north east lines",
    "crosshatch",
    "north west lines",
]

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def extract_weight(path: Path) -> float:
    m = re.search(r"weight_([0-9]+\.[0-9]+)", str(path))
    return float(m.group(1)) if m else 1.0


def extract_benchmark(stats_file: Path) -> str:
    return stats_file.parent.parent.parent.name


def parse_stats(stats_file: Path) -> Optional[tuple[float, float]]:
    in_dump = False
    last: Optional[tuple[float, float]] = None
    current_insts: Optional[float] = None
    current_cycles: Optional[float] = None

    try:
        with open(stats_file, "r", errors="replace") as f:
            for line in f:
                if "---------- Begin Simulation Statistics ----------" in line:
                    in_dump = True
                    current_insts = current_cycles = None
                    continue
                if "---------- End Simulation Statistics   ----------" in line:
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


def collect_ipc(base_dir: Path) -> dict[str, float]:
    stats_files = sorted(
        f for f in base_dir.glob("**/stats.txt")
        if "sensibility_analysis" not in f.parts
    )
    if not stats_files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}

    weighted_insts: dict[str, float] = defaultdict(float)
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
        weight = extract_weight(sf)
        weighted_insts[benchmark] += weight * insts
        weighted_cycles[benchmark] += weight * cycles

    return {
        bm: weighted_insts[bm] / weighted_cycles[bm]
        for bm in weighted_insts
        if weighted_cycles[bm] > 0
    }


def harmonic_mean(values: list[float]) -> float:
    if not values:
        return float("nan")
    return len(values) / sum(1.0 / v for v in values if v > 0)


def clean_label(benchmark: str) -> str:
    label = re.sub(r"^\d+\.", "", benchmark)
    label = re.sub(r"_s$", "", label)
    return label


# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------

def _escape_latex(s: str) -> str:
    return s.replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")


def generate_tikz(
    baseline_ipc: dict[str, float],
    approach_data: dict[str, dict[str, float]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_benchmarks = sorted(
        {bm for data in approach_data.values() for bm in data} & set(baseline_ipc)
    )
    x_labels = all_benchmarks + ["HarmonicMean"]
    approach_names = list(approach_data.keys())

    baseline_vals_all = [baseline_ipc[bm] for bm in all_benchmarks if bm in baseline_ipc]
    hm_baseline = harmonic_mean(baseline_vals_all)

    pct_data: dict[str, dict[str, float]] = {}
    ews_pct: dict[str, float] = {}
    for name, d in approach_data.items():
        pct: dict[str, float] = {}
        opt_vals: list[float] = []
        for bm in all_benchmarks:
            base = baseline_ipc.get(bm)
            val = d.get(bm)
            if base and val and base > 0:
                pct[bm] = (val / base - 1.0) * 100.0
                opt_vals.append(val)
        pct_data[name] = pct
        hm_opt = harmonic_mean(opt_vals)
        ews_pct[name] = (
            (hm_opt / hm_baseline - 1.0) * 100.0 if hm_baseline > 0 else float("nan")
        )

    coords: dict[str, list[str]] = {}
    for name in approach_names:
        pct = pct_data[name]
        vals_bm = [pct.get(bm, float("nan")) for bm in all_benchmarks]
        vals = vals_bm + [ews_pct[name]]
        coord_strs = [
            f"({label}, {v:.6f})"
            for label, v in zip(x_labels, vals)
            if v == v
        ]
        coords[name] = coord_strs

    sym_coords = ", ".join(x_labels)
    display_labels = [clean_label(lb) for lb in all_benchmarks] + [r"\textbf{HMean}"]
    xticklabels = ", ".join(display_labels)

    define_colors = ""
    for cname, r, g, b in BAR_COLORS:
        define_colors += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    addplot_lines = []
    for i, name in enumerate(approach_names):
        cname = BAR_COLORS[i % len(BAR_COLORS)][0]
        pattern = BAR_PATTERNS[i % len(BAR_PATTERNS)]
        escaped_name = _escape_latex(name)
        coord_body = "\n        ".join(coords[name])
        postaction = (
            f",\n        postaction={{pattern={pattern}, draw=black}}"
            if pattern
            else ""
        )
        addplot_lines.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw={cname}!60!black,\n"
            f"        line width=0.4pt{postaction},\n"
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
        r"\usetikzlibrary{patterns}" "\n"
        "\n"
        r"\pgfdeclarelayer{background}" "\n"
        r"\pgfsetlayers{background,main}" "\n"
        "\n"
        + define_colors
        + "\n"
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
        r"    ymin            = -35," "\n"
        r"    ymax            = 5," "\n"
        r"    ytick           = {-30, -20, -10, 0, 5}," "\n"
        r"    ylabel          = {Normalized performance}," "\n"
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
        r"            \fill[gray!60] ([xshift=-11pt]{axis cs:HarmonicMean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
        r"        \end{pgfonlayer}" "\n"
        r"    }," "\n"
        r"]" "\n"
        "\n"
        + addplot_str
        + "\n"
        "\n"
        r"\end{axis}" "\n"
        r"\end{tikzpicture}" "\n"
        r"\end{document}" "\n"
    )

    with open(output_path, "w") as f:
        f.write(tex)
    print(f"Saved {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not BASELINE_DIR.exists():
        print(f"ERROR: baseline directory not found: {BASELINE_DIR}")
        return
    print(f"Collecting IPC for {BASELINE_KEY} (L1 latency {L1_LATENCY}) …")
    baseline_ipc = collect_ipc(BASELINE_DIR)
    print(f"  → {len(baseline_ipc)} benchmarks found")

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

    all_bms = sorted(
        {bm for d in approach_data.values() for bm in d} & set(baseline_ipc)
    )
    header = f"{'Benchmark':<25}" + "".join(f"{n:>14}" for n in approach_data)
    print("\n" + header)
    print("-" * len(header))
    opt_ipc_lists: dict[str, list[float]] = {n: [] for n in approach_data}
    for bm in all_bms:
        row = f"{bm:<25}"
        base = baseline_ipc.get(bm, float("nan"))
        for name, d in approach_data.items():
            v = d.get(bm, float("nan"))
            pct = (
                (v / base - 1.0) * 100.0
                if base and base > 0 and v == v
                else float("nan")
            )
            row += f"{pct:>13.2f}%"
            if v == v:
                opt_ipc_lists[name].append(v)
        print(row)

    baseline_vals_all = [baseline_ipc[bm] for bm in all_bms if bm in baseline_ipc]
    hm_baseline = harmonic_mean(baseline_vals_all)
    ews_row = f"{'Harmonic Mean':<25}"
    for name in approach_data:
        hm_opt = harmonic_mean(opt_ipc_lists[name])
        ews_pct = (
            (hm_opt / hm_baseline - 1.0) * 100.0 if hm_baseline > 0 else float("nan")
        )
        ews_row += f"{ews_pct:>13.2f}%"
    print("-" * len(header))
    print(ews_row)

    generate_tikz(baseline_ipc, approach_data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
