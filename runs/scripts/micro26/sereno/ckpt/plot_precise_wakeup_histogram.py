#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) stacked bar chart showing, per
benchmark, the distribution (in %) of precise wakeups per cycle (0–12+) for
the Sereno (previously whisper) configuration.

Categories 0–12 map to the histogram buckets. Bucket 13 (overflow) is
aggregated into bucket 12 ("12+") since it is essentially zero.

Data source
-----------
  system.cpu.iew.precisseWakeUpHistogram::0
  system.cpu.iew.precisseWakeUpHistogram::1
  ...
  system.cpu.iew.precisseWakeUpHistogram::12

Read from:
  runs/output/micro26/sereno/ckpt/width8/{benchmark}/{simpoint}/m5out/stats.txt

Per-benchmark value: weighted arithmetic mean over simpoints.
The rightmost bar is the arithmetic mean across all benchmarks.

Output:
  runs/output/micro26/sereno/ckpt/graphs/precise_wakeup_histogram.tex
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[5]   # .../gem5-NTNU/
DATA_DIR   = ROOT / "runs/output/micro26/sereno/ckpt/width8"
OUTPUT_TEX = ROOT / "runs/output/micro26/sereno/ckpt/graphs/precise_wakeup_histogram.tex"

NUM_CATS  = 13   # buckets 0 .. 12  (bucket 13 = overflow, merged into 12)
STAT_BASE = "system.cpu.iew.precisseWakeUpHistogram"
# We read buckets 0..12 plus bucket 13 (overflow) to fold into 12+
STAT_KEYS = [f"{STAT_BASE}::{i}" for i in range(14)]   # 0..13
STAT_KEYS_SET = set(STAT_KEYS)

CATEGORY_LABELS = [str(i) for i in range(12)] + ["12"]

# Benchmarks and display labels – same order as all other micro26 scripts
BENCHMARKS_ORDER = [
    "600.perlbench_s",
    "602.gcc_s",
    "603.bwaves_s",
    "605.mcf_s",
    "607.cactuBSSN_s",
    "619.lbm_s",
    "620.omnetpp_s",
    "621.wrf_s",
    "623.xalancbmk_s",
    "625.x264_s",
    "627.cam4_s",
    "628.pop2_s",
    "631.deepsjeng_s",
    "641.leela_s",
    "644.nab_s",
    "648.exchange2_s",
    "649.fotonik3d_s",
    "654.roms_s",
    "657.xz_s",
]

DISPLAY_LABELS = [
    "perlbench", "gcc", "bwaves", "mcf", "cactuBSSN", "lbm",
    "omnetpp", "wrf", "xalancbmk", "x264", "cam4", "pop2",
    "deepsjeng", "leela", "nab", "exchange2", "fotonik3d", "roms", "xz",
]

# ------------------------------------------------------------------ #
# Colour palette: consistent with broadcast_port_utilization.py       #
#  cat0   : light gray + crosshatch-dots  →  "0 precise wakeups"     #
#  cat1   : clrSereno (Tableau blue)      →  "1 precise wakeup"      #
#  cat2-12: YlGnBu ColorBrewer sequence  (light yellow → dark navy)  #
# ------------------------------------------------------------------ #
_CAT_RGB = [
    (220, 220, 220),   # cat0  – light gray
    ( 31, 119, 180),   # cat1  – clrSereno / Tableau blue
    (255, 255, 217),   # cat2
    (237, 248, 177),   # cat3
    (199, 233, 180),   # cat4
    (127, 205, 187),   # cat5
    ( 65, 182, 196),   # cat6
    ( 29, 145, 192),   # cat7
    ( 34,  94, 168),   # cat8
    ( 37,  52, 148),   # cat9
    ( 20,  41, 113),   # cat10
    ( 12,  29,  99),   # cat11
    (  8,  29,  88),   # cat12+ – darkest
]
_PATTERNS  = ["crosshatch dots"] + [None] * 12
_PAT_COLS  = ["gray!60"]         + [None] * 12


# ------------------------------------------------------------------ #
# Stats parsing                                                        #
# ------------------------------------------------------------------ #

def extract_weight(path: Path) -> float:
    m = re.search(r'weight_([0-9]+\.[0-9]+)', str(path))
    return float(m.group(1)) if m else 1.0


def parse_stats(stats_file: Path) -> dict[str, float]:
    """Return the last simulation-dump values for the histogram buckets."""
    in_dump  = False
    current: dict[str, float] = {}
    last: dict[str, float]    = {}

    with open(stats_file, 'r', errors='replace') as f:
        for line in f:
            if '---------- Begin Simulation Statistics ----------' in line:
                in_dump = True
                current = {}
                continue
            if '---------- End Simulation Statistics   ----------' in line:
                if current:
                    last = current
                in_dump = False
                continue
            if not in_dump:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[0] in STAT_KEYS_SET:
                try:
                    current[parts[0]] = float(parts[1])
                except ValueError:
                    pass
    return last


def collect_data(
    base_dir: Path,
    debug_bm: str = "",
) -> dict[str, dict[str, float]]:
    """Return {benchmark: {stat_key: weighted_mean_count}} for buckets 0..12."""
    if not base_dir.exists():
        print(f"ERROR: data directory not found: {base_dir}")
        return {}

    stats_files = sorted(base_dir.glob("**/stats.txt"))
    if not stats_files:
        print(f"WARNING: no stats.txt found under {base_dir}")
        return {}

    weighted: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wsum:     dict[str, float]            = defaultdict(float)

    for sf in stats_files:
        benchmark = sf.parent.parent.parent.name
        if benchmark not in BENCHMARKS_ORDER:
            continue
        simpoint_dir = sf.parent.parent.name
        weight       = extract_weight(Path(simpoint_dir))
        vals         = parse_stats(sf)

        if not any(k in vals for k in STAT_KEYS):
            print(f"  WARNING: no precisseWakeUpHistogram stats in {sf}")
            continue

        if debug_bm and benchmark == debug_bm:
            counts = [vals.get(f"{STAT_BASE}::{i}", 0.0) for i in range(14)]
            total  = sum(counts)
            print(f"  simpoint : {simpoint_dir}")
            print(f"  weight   : {weight}")
            print(f"  raw counts : " + "  ".join(f"{i}={c:.0f}" for i, c in enumerate(counts)))
            print(f"  total    : {total:.0f}")

        for key in STAT_KEYS:
            if key in vals:
                weighted[benchmark][key] += weight * vals[key]
        wsum[benchmark] += weight

    # Build result: buckets 0..11 as-is; bucket 12 = bucket12 + bucket13
    result: dict[str, dict[str, float]] = {}
    for bm, d in weighted.items():
        if wsum[bm] <= 0:
            continue
        means: dict[str, float] = {k: d[k] / wsum[bm] for k in STAT_KEYS}
        # Fold overflow (bucket 13) into bucket 12
        key12 = f"{STAT_BASE}::12"
        key13 = f"{STAT_BASE}::13"
        means[key12] = means.get(key12, 0.0) + means.get(key13, 0.0)
        result[bm] = means

    if debug_bm and debug_bm in result:
        print(f"\n  -- Aggregated for {debug_bm} --")
        counts = [result[debug_bm].get(f"{STAT_BASE}::{i}", 0.0) for i in range(NUM_CATS)]
        total  = sum(counts)
        print(f"  weighted mean total : {total:.4f}")
        pct    = [100.0 * c / total for c in counts] if total > 0 else [0.0] * NUM_CATS
        print(f"  percentages : " + "  ".join(f"{i}={p:.2f}%" for i, p in enumerate(pct)))

    return result


def to_percentages(vals: dict[str, float]) -> list[float]:
    counts = [vals.get(f"{STAT_BASE}::{i}", 0.0) for i in range(NUM_CATS)]
    total  = sum(counts)
    if total <= 0:
        return [0.0] * NUM_CATS
    return [100.0 * c / total for c in counts]


def clean_label(name: str) -> str:
    label = re.sub(r'^\d+\.', '', name)
    label = re.sub(r'_s$', '', label)
    return label


# ------------------------------------------------------------------ #
# LaTeX / pgfplots generation                                          #
# ------------------------------------------------------------------ #

def _define_colors() -> str:
    lines = [
        f"\\definecolor{{clrPW{i}}}{{RGB}}{{{r},{g},{b}}}"
        for i, (r, g, b) in enumerate(_CAT_RGB)
    ]
    return "\n".join(lines) + "\n"


def generate_tikz(
    data: dict[str, dict[str, float]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    benchmarks = [bm for bm in BENCHMARKS_ORDER if bm in data]
    if not benchmarks:
        print("No benchmark data – nothing to plot.")
        return

    pct_data: dict[str, list[float]] = {bm: to_percentages(data[bm]) for bm in benchmarks}

    mean_pct = [
        sum(pct_data[bm][i] for bm in benchmarks) / len(benchmarks)
        for i in range(NUM_CATS)
    ]

    x_labels      = benchmarks + ["Mean"]
    display_labels = [clean_label(bm) for bm in benchmarks] + [r"\textbf{Mean}"]
    sym_coords    = ", ".join(x_labels)
    xticklabels   = ", ".join(display_labels)

    # Build addplot blocks (one per category)
    addplot_lines = []
    for i in range(NUM_CATS):
        cname   = f"clrPW{i}"
        pat     = _PATTERNS[i]
        patcol  = _PAT_COLS[i]

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

        cat_label = CATEGORY_LABELS[i]
        addplot_lines.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw=black!60,\n"
            f"        line width=0.3pt{postaction},\n"
            f"    ] coordinates {{\n"
            f"        {coord_body}\n"
            f"    }};\n"
            f"    \\addlegendentry{{{cat_label}}}"
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
        + _define_colors()
        + "\n"
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
        r"    tick align      = outside," "\n"
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
        r"        at={(0.5,1.02)}, anchor=south," "\n"
        r"        font=\normalsize," "\n"
        r"        cells={anchor=west}," "\n"
        r"        draw=none," "\n"
        r"        fill=white," "\n"
        r"        /tikz/every even column/.append style={column sep=8pt}," "\n"
        r"    }," "\n"
        r"    legend columns  = -1," "\n"
        r"    tick label style= {font=\normalsize}," "\n"
        r"    after end axis/.code={" "\n"
        r"        \begin{pgfonlayer}{background}" "\n"
        r"            \fill[gray!30] ([xshift=-9.5pt]{axis cs:Mean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
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


# ------------------------------------------------------------------ #
# Main                                                                 #
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Plot precise wakeup histogram distribution (Sereno): "
            "system.cpu.iew.precisseWakeUpHistogram per benchmark."
        )
    )
    parser.add_argument(
        "--debug", metavar="BENCHMARK", default="",
        help=(
            "Print per-simpoint raw counts for this benchmark "
            "(e.g. 600.perlbench_s)"
        ),
    )
    args = parser.parse_args()

    print(f"Collecting precisseWakeUpHistogram stats from:\n  {DATA_DIR}\n")
    if args.debug:
        print(f"DEBUG mode: showing raw numbers for '{args.debug}'\n")

    data = collect_data(DATA_DIR, debug_bm=args.debug)
    if not data:
        print("No data found – nothing to plot.")
        return

    benchmarks = [bm for bm in BENCHMARKS_ORDER if bm in data]
    print(f"Found {len(benchmarks)} benchmarks.\n")

    hdr = (
        f"{'Benchmark':<28}"
        + "".join(f"{f'k={i}':>8}" for i in range(NUM_CATS))
    )
    print(hdr)
    print("-" * len(hdr))

    all_pct = []
    for bm in benchmarks:
        pct = to_percentages(data[bm])
        all_pct.append(pct)
        row = f"{bm:<28}" + "".join(f"{v:>7.2f}%" for v in pct)
        print(row)

    means = [
        sum(p[i] for p in all_pct) / len(all_pct)
        for i in range(NUM_CATS)
    ]
    print("-" * len(hdr))
    print(f"{'Mean':<28}" + "".join(f"{v:>7.2f}%" for v in means))
    print()

    generate_tikz(data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
