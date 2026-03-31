#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) stacked bar chart showing, per
benchmark, the distribution (in %) of destination-register wakeup events by
the number of IQ dependents they wake up: 0, 1, 2, or 3-or-more.

Data source
-----------
  system.cpu.iew.wakeupDependents::0
  system.cpu.iew.wakeupDependents::1
  system.cpu.iew.wakeupDependents::2
  system.cpu.iew.wakeupDependents::3_or_more

Read from: runs/output/micro26/baseline/12B_-1P/width8/{benchmark}/{simpoint}/m5out/stats.txt

Per-benchmark value: weighted arithmetic mean over simpoints.
The rightmost bar is the arithmetic mean across all benchmarks.

Output: runs/output/micro26/baseline/12B_-1P/graphs/wakeup_dependents.tex
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[5]   # .../gem5-NTNU/
DATA_DIR   = ROOT / "runs/output/micro26/baseline/12B_-1P/width8"
OUTPUT_TEX = ROOT / "runs/output/micro26/baseline/12B_-1P/graphs/wakeup_dependents.tex"

STAT_KEYS = [
    "system.cpu.iew.wakeupDependents::0",
    "system.cpu.iew.wakeupDependents::1",
    "system.cpu.iew.wakeupDependents::2",
    "system.cpu.iew.wakeupDependents::3_or_more",
]

CATEGORY_LABELS = ["0", "1", "2", r"3 or more"]


def extract_weight(path: Path) -> float:
    m = re.search(r'weight_([0-9]+\.[0-9]+)', str(path))
    return float(m.group(1)) if m else 1.0


def parse_stats(stats_file: Path) -> dict[str, float]:
    in_dump   = False
    current: dict[str, float] = {}
    last: dict[str, float]    = {}

    with open(stats_file, 'r', errors='replace') as f:
        for line in f:
            if '---------- Begin Simulation Statistics ----------' in line:
                in_dump  = True
                current  = {}
                continue
            if '---------- End Simulation Statistics   ----------' in line:
                if current:
                    last = current
                in_dump = False
                continue
            if not in_dump:
                continue
            for key in STAT_KEYS:
                if line.startswith(key + ' ') or line.startswith(key + '\t'):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            current[key] = float(parts[1])
                        except ValueError:
                            pass
    return last


def collect_data(base_dir: Path, debug_bm: str = "") -> dict[str, dict[str, float]]:
    """Return {benchmark: {stat_key: weighted_mean}}."""
    if not base_dir.exists():
        print(f"ERROR: data directory not found: {base_dir}")
        return {}

    stats_files = sorted(base_dir.glob("**/stats.txt"))
    if not stats_files:
        print(f"WARNING: no stats.txt found under {base_dir}")
        return {}

    weighted: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wsum:     dict[str, float]            = defaultdict(float)

    SHORT = [k.split("::")[1] for k in STAT_KEYS]

    for sf in stats_files:
        benchmark = sf.parent.parent.parent.name
        weight    = extract_weight(sf.parent.parent.name)
        vals      = parse_stats(sf)
        if not vals:
            print(f"  WARNING: no wakeupDependents stats in {sf}")
            continue

        if debug_bm and benchmark == debug_bm:
            raw     = [vals.get(k, 0.0) for k in STAT_KEYS]
            total_r = sum(raw)
            print(f"  simpoint : {sf.parent.parent.name}")
            print(f"  weight   : {weight}")
            print(f"  raw counts  : " + "  ".join(f"{s}={v:.0f}" for s, v in zip(SHORT, raw)))
            print(f"  raw total   : {total_r:.0f}")
            if total_r > 0:
                print(f"  raw pct     : " + "  ".join(f"{s}={100*v/total_r:.2f}%" for s, v in zip(SHORT, raw)))
            print(f"  weighted    : " + "  ".join(f"{s}={weight*v:.2f}" for s, v in zip(SHORT, raw)))
            print()

        for key in STAT_KEYS:
            if key in vals:
                weighted[benchmark][key] += weight * vals[key]
        wsum[benchmark] += weight

    result: dict[str, dict[str, float]] = {}
    for bm, d in weighted.items():
        if wsum[bm] <= 0:
            continue
        result[bm] = {k: d[k] / wsum[bm] for k in STAT_KEYS}

    if debug_bm and debug_bm in weighted:
        print(f"  --- Aggregated for {debug_bm} ---")
        print(f"  total weight sum : {wsum[debug_bm]:.6f}")
        wm      = result[debug_bm]
        acc     = {k: weighted[debug_bm][k] for k in STAT_KEYS}
        total_wm = sum(wm.values())
        print(f"  weighted sums   : " + "  ".join(f"{s}={acc[k]:.2f}" for s, k in zip(SHORT, STAT_KEYS)))
        print(f"  weighted means  : " + "  ".join(f"{s}={wm[k]:.4f}" for s, k in zip(SHORT, STAT_KEYS)))
        print(f"  weighted mean total : {total_wm:.4f}")
        pct = [100.0 * wm[k] / total_wm for k in STAT_KEYS] if total_wm > 0 else [0.0]*4
        print(f"  final pct       : " + "  ".join(f"{s}={p:.2f}%" for s, p in zip(SHORT, pct)))
        print()

    return result


def clean_label(name: str) -> str:
    label = re.sub(r'^\d+\.', '', name)
    label = re.sub(r'_s$', '', label)
    return label


def to_percentages(vals: dict[str, float]) -> list[float]:
    counts = [vals.get(k, 0.0) for k in STAT_KEYS]
    total  = sum(counts)
    if total <= 0:
        return [0.0] * len(STAT_KEYS)
    return [100.0 * c / total for c in counts]


def generate_tikz(data: dict[str, dict[str, float]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    benchmarks = sorted(data.keys())

    pct_data: dict[str, list[float]] = {}
    for bm in benchmarks:
        pct_data[bm] = to_percentages(data[bm])

    mean_pct = []
    for i in range(len(STAT_KEYS)):
        mean_pct.append(sum(pct_data[bm][i] for bm in benchmarks) / len(benchmarks))

    x_labels     = benchmarks + ["Mean"]
    display_labels = [clean_label(bm) for bm in benchmarks] + ["Mean"]
    sym_coords   = ", ".join(x_labels)
    xticklabels  = ", ".join(display_labels)

    colors = [
        ("clrDep0",    "F2F2F2"),
        ("clrDep1",    "B2ABD2"),
        ("clrDep2",    "7570B3"),
        ("clrDep3",    "3F007D"),
    ]
    patterns = [
        None,
        "dots",
        "north east lines",
        "crosshatch",
    ]
    pattern_colors = [
        None,
        "black!40",
        "black!40",
        "white!30",
    ]

    define_colors = ""
    for cname, hex_val in colors:
        r = int(hex_val[0:2], 16)
        g = int(hex_val[2:4], 16)
        b = int(hex_val[4:6], 16)
        define_colors += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    addplot_lines = []
    for i, cat_label in enumerate(CATEGORY_LABELS):
        cname   = colors[i][0]
        pat     = patterns[i]
        patcol  = pattern_colors[i]

        coords = []
        for bm in benchmarks:
            coords.append(f"({bm}, {pct_data[bm][i]:.4f})")
        coords.append(f"(Mean, {mean_pct[i]:.4f})")
        coord_body = "\n        ".join(coords)

        if pat:
            postaction = (
                f",\n        postaction={{pattern={pat},"
                f" pattern color={patcol}}}"
            )
        else:
            postaction = ""

        escaped = cat_label.replace('_', r'\_')
        addplot_lines.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw=black!60,\n"
            f"        line width=0.3pt{postaction},\n"
            f"    ] coordinates {{\n"
            f"        {coord_body}\n"
            f"    }};\n"
            f"    \\addlegendentry{{{escaped}}}"
        )

    addplot_str = "\n\n".join(addplot_lines)

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
        r"        \draw[#1, draw=black!60, line width=0.3pt]" "\n"
        r"            (0pt,-1pt) rectangle (5pt,4pt);" "\n"
        r"    }," "\n"
        r"}" "\n"
        "\n"
        r"\begin{document}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"\begin{axis}[" "\n"
        r"    ybar stacked," "\n"
        r"    bar width       = 18pt," "\n"
        r"    width           = 15.5cm," "\n"
        r"    height          = 7cm," "\n"
        r"    enlarge x limits= 0.05," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    tick align      = outside," + "\n"
        r"    x tick label style = {rotate=90, anchor=east, font=\normalsize}," "\n"
        r"    ymin            = 0," "\n"
        r"    ymax            = 100," "\n"
        r"    ytick           = {0, 20, 40, 60, 80, 100}," "\n"
        r"    yticklabel      = {\pgfmathprintnumber{\tick}\%}," "\n"
        r"    ylabel style    = {font=\normalsize}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    legend style    = {" "\n"
        r"        at={(0.5,1.1)}, anchor=south," "\n"
        r"        font=\normalsize," "\n"
        r"        cells={anchor=west}," "\n"
        r"        draw=none," "\n"
        r"        fill=white," "\n"
        r"        /tikz/every even column/.append style={column sep=8pt}," "\n"
        r"    }," "\n"
        r"    legend columns  = -1," "\n"
        r"    tick label style= {font=\normalsize}," "\n"
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot wakeup dependents distribution.")
    parser.add_argument(
        "--debug", metavar="BENCHMARK", default="",
        help="Print per-simpoint raw counts and calculations for this benchmark (e.g. 600.perlbench_s)",
    )
    args = parser.parse_args()

    print(f"Collecting wakeupDependents stats from {DATA_DIR} ...")
    if args.debug:
        print(f"DEBUG mode: showing all numbers for '{args.debug}'\n")
    data = collect_data(DATA_DIR, debug_bm=args.debug)
    if not data:
        print("No data found – nothing to plot.")
        return

    benchmarks = sorted(data.keys())
    print(f"\nFound {len(benchmarks)} benchmarks:")
    header = f"{'Benchmark':<30}" + "".join(f"{c:>12}" for c in ["0 (%)", "1 (%)", "2 (%)", "3+ (%)"])
    print(header)
    print("-" * len(header))
    for bm in benchmarks:
        pct = to_percentages(data[bm])
        row = f"{bm:<30}" + "".join(f"{v:>11.2f}%" for v in pct)
        print(row)

    all_pct = [to_percentages(data[bm]) for bm in benchmarks]
    means   = [sum(p[i] for p in all_pct) / len(all_pct) for i in range(len(STAT_KEYS))]
    print("-" * len(header))
    print(f"{'Mean':<30}" + "".join(f"{v:>11.2f}%" for v in means))

    generate_tikz(data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
