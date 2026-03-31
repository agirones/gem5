#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) bar chart showing, per benchmark,
the fraction of broadcasts that are non-delayed (i.e. happen the same cycle
execution finishes) in the Sereno configuration.

  non_delayed_ratio (%) = sameCycleBroadcast / broadcastWakeUp * 100

A high ratio shows that most broadcasts in Sereno are non-delayed, meaning
the wakeup logic can fire in the same cycle as execution completes.

Data source
-----------
  system.cpu.iew.sameCycleBroadcast
  system.cpu.iew.broadcastWakeUp

Read from:
  runs/output/micro26/whisper/1B_2P/width8/{benchmark}/{simpoint}/m5out/stats.txt

Per-benchmark value: ratio of weighted-sum(sameCycleBroadcast) /
                                  weighted-sum(broadcastWakeUp).
The rightmost bar is the arithmetic mean across all per-benchmark ratios.

Output:
  runs/output/micro26/whisper/1B_2P/graphs/non_delayed_broadcasts.tex
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[5]   # .../gem5-NTNU/
DATA_DIR   = ROOT / "runs/output/micro26/whisper/1B_2P/width8"
OUTPUT_TEX = ROOT / "runs/output/micro26/whisper/1B_2P/graphs/non_delayed_broadcasts.tex"

KEY_SAME_CYCLE = "system.cpu.iew.sameCycleBroadcast"
KEY_BROADCAST  = "system.cpu.iew.broadcastWakeUp"
STAT_KEYS      = [KEY_SAME_CYCLE, KEY_BROADCAST]

# Benchmarks to include (same 19 used in other micro26 graphs).
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


def extract_weight(path: Path) -> float:
    m = re.search(r'weight_([0-9]+\.[0-9]+)', str(path))
    return float(m.group(1)) if m else 1.0


def parse_stats(stats_file: Path, debug: bool = False) -> dict[str, float]:
    """Return the last simulation-dump values for KEY_SAME_CYCLE and KEY_BROADCAST."""
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
            for key in STAT_KEYS:
                if line.startswith(key):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            current[key] = float(parts[1])
                        except ValueError:
                            pass

    if debug:
        print(f"      {stats_file.parent.parent.name}")
        print(f"        sameCycleBroadcast : {last.get(KEY_SAME_CYCLE, 'N/A')}")
        print(f"        broadcastWakeUp    : {last.get(KEY_BROADCAST, 'N/A')}")

    return last


def collect_data(
    base_dir: Path,
    debug_bm: str = "",
) -> dict[str, float]:
    """
    Return {benchmark: non_delayed_ratio_percent} where the ratio is computed
    from the weighted sums of the two raw counters over all simpoints.
    """
    if not base_dir.exists():
        print(f"ERROR: data directory not found: {base_dir}")
        return {}

    stats_files = sorted(base_dir.glob("**/stats.txt"))
    if not stats_files:
        print(f"WARNING: no stats.txt found under {base_dir}")
        return {}

    w_same_cycle: dict[str, float] = defaultdict(float)
    w_broadcast:  dict[str, float] = defaultdict(float)

    for sf in stats_files:
        benchmark = sf.parent.parent.parent.name
        if benchmark not in BENCHMARKS_ORDER:
            continue
        simpoint_dir = sf.parent.parent.name
        weight       = extract_weight(Path(simpoint_dir))
        debug        = (debug_bm and benchmark == debug_bm)
        vals         = parse_stats(sf, debug=debug)

        if KEY_SAME_CYCLE not in vals or KEY_BROADCAST not in vals:
            print(f"  WARNING: missing stats in {sf}")
            continue

        w_same_cycle[benchmark] += weight * vals[KEY_SAME_CYCLE]
        w_broadcast[benchmark]  += weight * vals[KEY_BROADCAST]

    result: dict[str, float] = {}
    for bm in BENCHMARKS_ORDER:
        b = w_broadcast.get(bm, 0.0)
        s = w_same_cycle.get(bm, 0.0)
        if b <= 0.0:
            print(f"  WARNING: zero broadcastWakeUp for {bm}, skipping")
            continue
        result[bm] = 100.0 * s / b

    return result


def generate_tikz(data: dict[str, float], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build ordered list of benchmarks present in data
    benchmarks   = [bm for bm in BENCHMARKS_ORDER if bm in data]
    bench_labels = [DISPLAY_LABELS[BENCHMARKS_ORDER.index(bm)] for bm in benchmarks]
    ratios       = [data[bm] for bm in benchmarks]
    mean_ratio   = sum(ratios) / len(ratios) if ratios else 0.0

    x_labels    = benchmarks + ["Mean"]
    display_lbl = bench_labels + ["Mean"]
    sym_coords  = ", ".join(x_labels)
    xticklabels = ", ".join(display_lbl)

    coords = []
    for bm, r in zip(benchmarks, ratios):
        coords.append(f"        ({bm}, {r:.4f})")
    coords.append(f"        (Mean, {mean_ratio:.4f})")
    coord_str = "\n".join(coords)

    # Y-axis: fixed 0–100 % range with steps of 20
    y_max    = 100
    y_step   = 20
    ytick    = list(range(0, y_max + 1, y_step))
    ytick_str = ", ".join(str(v) for v in ytick)

    # clrSereno: Tableau Blue — consistent with all other micro26 graphs
    tex = (
        r"\documentclass[tikz]{standalone}" + "\n"
        r"\usepackage{pgfplots}" + "\n"
        r"\pgfplotsset{compat=1.18}" + "\n"
        "\n"
        r"\definecolor{clrSereno}{RGB}{31,119,180}" + "\n"
        "\n"
        r"\begin{document}" + "\n"
        r"\begin{tikzpicture}" + "\n"
        r"\begin{axis}[" + "\n"
        r"    ybar," + "\n"
        r"    bar width       = 18pt," + "\n"
        r"    width           = 15.5cm," + "\n"
        r"    height          = 7cm," + "\n"
        r"    enlarge x limits= 0.05," + "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," + "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    tick align      = outside," + "\n"
        r"    x tick label style = {rotate=90, anchor=east, font=\normalsize}," + "\n"
        r"    ymin            = 0," + "\n"
        f"    ymax            = {y_max},\n"
        f"    ytick           = {{{ytick_str}}},\n"
        r"    yticklabel      = {\pgfmathprintnumber{\tick}\%}," + "\n"
        r"    ylabel          = {Non-Delayed Broadcasts}," + "\n"
        r"    ylabel style    = {font=\normalsize}," + "\n"
        r"    ymajorgrids     = true," + "\n"
        r"    grid style      = {dashed, gray!30}," + "\n"
        r"    axis line style = {gray!60}," + "\n"
        r"    tick style      = {gray!60}," + "\n"
        r"    after end axis/.code={" + "\n"
        r"        \draw[gray!70, dashed, line width=0.8pt]" + "\n"
        r"            ([xshift=-9.5pt]{axis cs:Mean,\pgfkeysvalueof{/pgfplots/ymin}})" + "\n"
        r"            -- ([xshift=-9.5pt]{axis cs:Mean,\pgfkeysvalueof{/pgfplots/ymax}});" + "\n"
        r"    }," + "\n"
        r"    tick label style= {font=\normalsize}," + "\n"
        r"]" + "\n"
        "\n"
        r"    \addplot[" + "\n"
        r"        fill=clrSereno," + "\n"
        r"        draw=clrSereno!60!black," + "\n"
        r"        line width=0.4pt," + "\n"
        r"    ] coordinates {" + "\n"
        + coord_str + "\n"
        r"    };" + "\n"
        "\n"
        r"\end{axis}" + "\n"
        r"\end{tikzpicture}" + "\n"
        r"\end{document}" + "\n"
    )

    with open(output_path, 'w') as f:
        f.write(tex)
    print(f"Saved {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Plot the fraction of non-delayed broadcasts (Sereno): "
            "sameCycleBroadcast / broadcastWakeUp per benchmark."
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

    print(f"Collecting broadcast stats from {DATA_DIR} ...")
    if args.debug:
        print(f"DEBUG mode: showing raw numbers for '{args.debug}'\n")

    data = collect_data(DATA_DIR, debug_bm=args.debug)
    if not data:
        print("No data found – nothing to plot.")
        return

    benchmarks = [bm for bm in BENCHMARKS_ORDER if bm in data]
    print(f"\nFound {len(benchmarks)} benchmarks:")
    header = f"{'Benchmark':<30}  {'Non-Delayed (%)':>17}"
    print(header)
    print("-" * len(header))
    for bm in benchmarks:
        print(f"{bm:<30}  {data[bm]:>16.3f}%")

    mean_val = sum(data[bm] for bm in benchmarks) / len(benchmarks)
    print("-" * len(header))
    print(f"{'Mean':<30}  {mean_val:>16.3f}%")

    generate_tikz(data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
