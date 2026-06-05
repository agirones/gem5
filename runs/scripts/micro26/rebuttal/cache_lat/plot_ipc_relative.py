#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) grouped bar chart showing the
IPC change (in %) of Sereno relative to the baseline for each L1 cache
latency configuration (2, 3, 4).

Per-benchmark value: ((sereno_IPC / baseline_IPC) - 1) * 100

The rightmost group shows the Equal-Work Speedup (EWS) as defined by
Eeckhout (2024): EWS = ((HM_sereno / HM_baseline) - 1) * 100
where HM_* is the harmonic mean of raw IPCs over all benchmarks.
Harmonic means are used exclusively — no arithmetic or geometric means.

Data sources (matched latency per bar group):
  Baseline : runs/output/micro26/rebuttal/cache_lat/baseline/{2,3,4}
  Sereno   : runs/output/micro26/rebuttal/cache_lat/sereno/{2,3,4}

IPC per benchmark is computed as sum(weight * simInsts) /
sum(weight * numCycles) over simpoints (weights are embedded in the
simpoint directory names and sum to 1).

Output: runs/output/micro26/rebuttal/cache_lat/ipc_relative.tex
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
BASELINE_ROOT = CACHE_LAT_DIR / "baseline"
SERENO_ROOT = CACHE_LAT_DIR / "sereno"

L1_LATENCIES = [2, 3, 4]

OUTPUT_TEX = CACHE_LAT_DIR / "ipc_relative.tex"

INSTS_STAT = "simInsts"
CYCLES_STAT = "system.cpu.numCycles"

# One style entry per L1 latency (2, 3, 4).
BAR_COLORS: list[tuple[str, int, int, int]] = [
    ("clrLat2", 31, 119, 180),   # tableau blue
    ("clrLat3", 255, 127, 14),   # tableau orange
    ("clrLat4", 44, 160, 44),    # tableau green
]

BAR_PATTERNS: list[Optional[str]] = [
    None,
    "north east lines",
    "crosshatch",
]

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def extract_weight(path: Path) -> float:
    """Return simpoint weight from directory name, defaulting to 1.0."""
    m = re.search(r"weight_([0-9]+\.[0-9]+)", str(path))
    return float(m.group(1)) if m else 1.0


def extract_benchmark(stats_file: Path) -> str:
    """
    Return the benchmark name from a stats.txt path.

    Expected layout:
        {base_dir}/width8/{benchmark}/{simpoint_dir}/m5out/stats.txt
    """
    return stats_file.parent.parent.parent.name


def parse_stats(stats_file: Path) -> Optional[tuple[float, float]]:
    """
    Return (simInsts, numCycles) from the final stats dump.
    """
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
    """
    Walk *base_dir* and return {benchmark: weighted_IPC}.

    Per-benchmark IPC = sum(weight * simInsts) / sum(weight * numCycles).
    """
    stats_files = sorted(f for f in base_dir.glob("**/stats.txt"))
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
    """
    Strip the leading SPEC number + dot and trailing '_s' suffix.
    E.g. '600.perlbench_s' -> 'perlbench', '625.x264_s' -> 'x264'.
    """
    label = re.sub(r"^\d+\.", "", benchmark)
    label = re.sub(r"_s$", "", label)
    return label


# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------

def _escape_latex(s: str) -> str:
    return s.replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")


def generate_tikz(
    baseline_by_latency: dict[int, dict[str, float]],
    sereno_by_latency: dict[int, dict[str, float]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_benchmarks = sorted(
        {bm for data in sereno_by_latency.values() for bm in data}
        & {bm for data in baseline_by_latency.values() for bm in data}
    )
    x_labels = all_benchmarks + ["HarmonicMean"]

    pct_data: dict[int, dict[str, float]] = {}
    ews_pct: dict[int, float] = {}

    for latency in L1_LATENCIES:
        baseline_ipc = baseline_by_latency.get(latency, {})
        sereno_ipc = sereno_by_latency.get(latency, {})

        pct: dict[str, float] = {}
        sereno_vals: list[float] = []
        baseline_vals: list[float] = []

        for bm in all_benchmarks:
            base = baseline_ipc.get(bm)
            val = sereno_ipc.get(bm)
            if base and val and base > 0:
                pct[bm] = (val / base - 1.0) * 100.0
                sereno_vals.append(val)
                baseline_vals.append(base)

        pct_data[latency] = pct
        hm_sereno = harmonic_mean(sereno_vals)
        hm_baseline = harmonic_mean(baseline_vals)
        ews_pct[latency] = (
            (hm_sereno / hm_baseline - 1.0) * 100.0 if hm_baseline > 0 else float("nan")
        )

    coords: dict[int, list[str]] = {}
    for latency in L1_LATENCIES:
        pct = pct_data.get(latency, {})
        vals_bm = [pct.get(bm, float("nan")) for bm in all_benchmarks]
        vals = vals_bm + [ews_pct.get(latency, float("nan"))]
        coord_strs = [
            f"({label}, {v:.6f})"
            for label, v in zip(x_labels, vals)
            if v == v
        ]
        coords[latency] = coord_strs

    sym_coords = ", ".join(x_labels)
    display_labels = [clean_label(lb) for lb in all_benchmarks] + [r"\textbf{HMean}"]
    xticklabels = ", ".join(display_labels)

    define_colors = ""
    for cname, r, g, b in BAR_COLORS:
        define_colors += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    addplot_lines = []
    for i, latency in enumerate(L1_LATENCIES):
        cname = BAR_COLORS[i % len(BAR_COLORS)][0]
        pattern = BAR_PATTERNS[i % len(BAR_PATTERNS)]
        coord_body = "\n        ".join(coords.get(latency, []))
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
            f"    \\addlegendentry{{L1 latency {latency}}}"
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
    baseline_by_latency: dict[int, dict[str, float]] = {}
    sereno_by_latency: dict[int, dict[str, float]] = {}

    for latency in L1_LATENCIES:
        baseline_dir = BASELINE_ROOT / str(latency)
        sereno_dir = SERENO_ROOT / str(latency)

        if not baseline_dir.exists():
            print(f"SKIP baseline latency {latency}: directory not found ({baseline_dir})")
            continue
        if not sereno_dir.exists():
            print(f"SKIP sereno latency {latency}: directory not found ({sereno_dir})")
            continue

        print(f"Collecting IPC for baseline L1 latency {latency} …")
        baseline_ipc = collect_ipc(baseline_dir)
        print(f"  → {len(baseline_ipc)} benchmarks found")

        print(f"Collecting IPC for sereno L1 latency {latency} …")
        sereno_ipc = collect_ipc(sereno_dir)
        print(f"  → {len(sereno_ipc)} benchmarks found")

        baseline_by_latency[latency] = baseline_ipc
        sereno_by_latency[latency] = sereno_ipc

    if not baseline_by_latency or not sereno_by_latency:
        print("No data found – nothing to plot.")
        return

    all_bms = sorted(
        {bm for data in sereno_by_latency.values() for bm in data}
        & {bm for data in baseline_by_latency.values() for bm in data}
    )

    header = f"{'Benchmark':<25}" + "".join(f"{'L1=' + str(lat):>14}" for lat in L1_LATENCIES)
    print("\n" + header)
    print("-" * len(header))

    sereno_ipc_lists: dict[int, list[float]] = {lat: [] for lat in L1_LATENCIES}
    baseline_ipc_lists: dict[int, list[float]] = {lat: [] for lat in L1_LATENCIES}

    for bm in all_bms:
        row = f"{bm:<25}"
        for latency in L1_LATENCIES:
            base = baseline_by_latency.get(latency, {}).get(bm, float("nan"))
            val = sereno_by_latency.get(latency, {}).get(bm, float("nan"))
            pct = (
                (val / base - 1.0) * 100.0
                if base and base > 0 and val == val
                else float("nan")
            )
            row += f"{pct:>13.2f}%"
            if val == val:
                sereno_ipc_lists[latency].append(val)
            if base == base and base > 0:
                baseline_ipc_lists[latency].append(base)
        print(row)

    ews_row = f"{'Harmonic Mean':<25}"
    for latency in L1_LATENCIES:
        hm_sereno = harmonic_mean(sereno_ipc_lists[latency])
        hm_baseline = harmonic_mean(baseline_ipc_lists[latency])
        ews_pct = (
            (hm_sereno / hm_baseline - 1.0) * 100.0 if hm_baseline > 0 else float("nan")
        )
        ews_row += f"{ews_pct:>13.2f}%"
    print("-" * len(header))
    print(ews_row)

    generate_tikz(baseline_by_latency, sereno_by_latency, OUTPUT_TEX)


if __name__ == "__main__":
    main()
