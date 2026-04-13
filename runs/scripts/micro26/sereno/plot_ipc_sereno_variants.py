#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) grouped bar chart showing the
IPC change (in %) of each Sereno variant relative to the Sereno/ckpt baseline.
Negative values represent performance degradation.

Per-benchmark value: ((variant_IPC / ckpt_IPC) - 1) * 100

The rightmost group shows the Equal-Work Speedup (EWS) as defined by
Eeckhout (2024): EWS = ((HM_variant / HM_baseline) - 1) * 100
where HM_* is the harmonic mean of raw IPCs over all benchmarks.
Harmonic means are used exclusively — no arithmetic or geometric means.

Variants compared
-----------------
  Baseline  : runs/output/micro26/baseline/12B_-1P  (reference = 0 %)
  ckpt      : runs/output/micro26/sereno/ckpt
  sqbcast   : runs/output/micro26/sereno/sqbcast
  stale     : runs/output/micro26/sereno/stale

IPC per benchmark is computed as a weighted arithmetic mean over simpoints
(weights are embedded in the simpoint directory names and sum to 1).

Output: a standalone .tex file importable with \input{} in an Overleaf
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

# Sereno variants to compare against the baseline.
APPROACHES: dict[str, Path] = {
    "ckpt":    ROOT / "runs/output/micro26/sereno/ckpt",
    "sqbcast": ROOT / "runs/output/micro26/sereno/sqbcast",
    "stale":   ROOT / "runs/output/micro26/sereno/stale",
}

OUTPUT_DIR = ROOT / "runs/output/micro26/graphs"
OUTPUT_TEX = OUTPUT_DIR / "ipc_relative_sereno_variants.tex"

INSTS_STAT  = "simInsts"
CYCLES_STAT = "system.cpu.numCycles"

# Set to a benchmark name (e.g. "pop2_s") to print per-simpoint IPC details.
DEBUG_BM: Optional[str] = "649.fotonik3d_s"

# Tableau-10 inspired palette — order matches APPROACHES above.
BAR_COLORS: list[tuple[str, int, int, int]] = [
    ("clrCkpt",    31, 119, 180),   # tableau blue
    ("clrSqbcast", 214,  39,  40),   # tableau red
    ("clrStale",    44, 160,  44),   # tableau green
]

# Hatch patterns per approach (None = solid fill only).
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
    current_insts:  Optional[float] = None
    current_cycles: Optional[float] = None

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

def collect_ipc(base_dir: Path, label: str = "") -> tuple[dict[str, float], list[float]]:
    """
    Walk *base_dir* and return ({benchmark: IPC}, [all_raw_IPCs]).

    Per-benchmark IPC = sum(weight * simInsts) / sum(weight * numCycles).
    all_raw_IPCs contains per-simpoint simInsts/numCycles values (unweighted).
    """
    stats_files = sorted(
        f for f in base_dir.glob("**/stats.txt")
        if "sensibility_analysis" not in f.parts
    )
    if not stats_files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}, []

    weighted_insts:  dict[str, float] = defaultdict(float)
    weighted_cycles: dict[str, float] = defaultdict(float)
    all_raw_ipcs: list[float] = []

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
        all_raw_ipcs.append(insts / cycles)

        if DEBUG_BM and benchmark == DEBUG_BM:
            simpoint = sf.parent.parent.name
            print(
                f"  [DEBUG {label or base_dir.name}] [{benchmark}]"
                f"  simpoint={simpoint}"
                f"  weight={weight:.6f}"
                f"  insts={insts:.0f}  cycles={cycles:.0f}"
                f"  ipc={insts/cycles:.6f}"
            )

    result = {
        bm: weighted_insts[bm] / weighted_cycles[bm]
        for bm in weighted_insts
        if weighted_cycles[bm] > 0
    }

    if DEBUG_BM and DEBUG_BM in result:
        print(
            f"  [DEBUG {label or base_dir.name}] [{DEBUG_BM}]"
            f"  weighted_insts={weighted_insts[DEBUG_BM]:.0f}"
            f"  weighted_cycles={weighted_cycles[DEBUG_BM]:.0f}"
            f"  IPC={result[DEBUG_BM]:.6f}"
        )

    return result, all_raw_ipcs


def harmonic_mean(values: list[float]) -> float:
    if not values:
        return float('nan')
    return len(values) / sum(1.0 / v for v in values if v > 0)


def clean_label(benchmark: str) -> str:
    """
    Strip the leading SPEC number + dot and trailing '_s' suffix.
    E.g. '600.perlbench_s' -> 'perlbench', '625.x264_s' -> 'x264'.
    """
    label = re.sub(r'^\d+\.', '', benchmark)
    label = re.sub(r'_s$', '', label)
    return label

# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------

def _escape_latex(s: str) -> str:
    return s.replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')


def generate_tikz(
    baseline_ipc: dict[str, float],
    approach_data: dict[str, dict[str, float]],
    output_path: Path,
    baseline_raw_ipcs: list[float] = [],
    approach_raw_ipcs: dict[str, list[float]] = {},
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_benchmarks: list[str] = sorted(
        {bm for data in approach_data.values() for bm in data}
        & set(baseline_ipc)          # only benchmarks present in baseline too
    )
    x_labels = all_benchmarks + ["HarmonicMean"]
    approach_names = list(approach_data.keys())

    # Harmonic mean of baseline IPCs across all raw simpoint measurements.
    hm_baseline = harmonic_mean(baseline_raw_ipcs) if baseline_raw_ipcs else harmonic_mean(
        [baseline_ipc[bm] for bm in all_benchmarks if bm in baseline_ipc]
    )

    # Per-benchmark percentage change and EWS for each approach.
    pct_data: dict[str, dict[str, float]] = {}
    ews_pct:  dict[str, float] = {}
    for name, d in approach_data.items():
        pct: dict[str, float] = {}
        for bm in all_benchmarks:
            base = baseline_ipc.get(bm)
            val  = d.get(bm)
            if base and val and base > 0:
                pct[bm] = (val / base - 1.0) * 100.0
        pct_data[name] = pct
        # EWS: ratio of harmonic means across all raw simpoint measurements
        raw = approach_raw_ipcs.get(name, [])
        hm_opt = harmonic_mean(raw) if raw else harmonic_mean(
            [v for v in d.values() if v > 0]
        )
        ews_pct[name] = (hm_opt / hm_baseline - 1.0) * 100.0 if hm_baseline > 0 else float('nan')

    # Build per-approach coordinate lists.
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

    # symbolic x coords use the raw benchmark keys (pgfplots needs them to
    # match the coordinate labels in \addplot).
    sym_coords = ", ".join(x_labels)

    # Display labels: clean human-readable names.
    display_labels = [clean_label(lb) for lb in all_benchmarks] + [r"\textbf{Harmonic Mean}"]
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
        postaction = f",\n        postaction={{pattern={pattern}, draw=black}}" if pattern else ""
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
        r"    ymin            = -5," "\n"
        r"    ymax            = 2," "\n"
        r"    ytick           = {-5, -4, -3, -2, -1, 0, 1, 2}," "\n"
        r"    extra y ticks   = {0}," "\n"
        r"    extra y tick style = {" "\n"
        r"        grid=major," "\n"
        r"        grid style={solid, black!50, line width=0.6pt}," "\n"
        r"    }," "\n"
        r"    ylabel          = {Normalized performance}," "\n"
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
        r"            \fill[gray!15] ([xshift=-10pt]{axis cs:HarmonicMean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
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
    # Collect baseline IPC (sereno/ckpt).
    if not BASELINE_DIR.exists():
        print(f"ERROR: baseline directory not found: {BASELINE_DIR}")
        return
    print(f"Collecting IPC for {BASELINE_KEY} …")
    baseline_ipc, baseline_raw_ipcs = collect_ipc(BASELINE_DIR, label=BASELINE_KEY)
    print(f"  → {len(baseline_ipc)} benchmarks found")

    # Collect non-baseline Sereno variants.
    approach_data: dict[str, dict[str, float]] = {}
    approach_raw_ipcs: dict[str, list[float]] = {}
    for name, base_dir in APPROACHES.items():
        if not base_dir.exists():
            print(f"SKIP {name}: directory not found ({base_dir})")
            continue
        print(f"Collecting IPC for {name} …")
        data, raw_ipcs = collect_ipc(base_dir, label=name)
        print(f"  → {len(data)} benchmarks found")
        approach_data[name] = data
        approach_raw_ipcs[name] = raw_ipcs

    if not approach_data:
        print("No data found – nothing to plot.")
        return

    # Print per-benchmark IPC change (%) summary.
    all_bms = sorted(
        {bm for d in approach_data.values() for bm in d} & set(baseline_ipc)
    )
    header = f"{'Benchmark':<25}" + "".join(f"{n:>14}" for n in approach_data)
    print("\n" + header)
    print("-" * len(header))
    for bm in all_bms:
        row = f"{bm:<25}"
        base = baseline_ipc.get(bm, float('nan'))
        for name, d in approach_data.items():
            v = d.get(bm, float('nan'))
            pct = (v / base - 1.0) * 100.0 if base and base > 0 and v == v else float('nan')
            row += f"{pct:>13.2f}%"
        print(row)

    # EWS row using harmonic mean of all raw simpoint IPC measurements.
    hm_baseline = harmonic_mean(baseline_raw_ipcs)
    ews_row = f"{'Harmonic Mean':<25}"
    for name in approach_data:
        hm_opt = harmonic_mean(approach_raw_ipcs[name])
        ews_pct = (hm_opt / hm_baseline - 1.0) * 100.0 if hm_baseline > 0 else float('nan')
        ews_row += f"{ews_pct:>13.2f}%"
    print("-" * len(header))
    print(ews_row)

    generate_tikz(baseline_ipc, approach_data, OUTPUT_TEX, baseline_raw_ipcs, approach_raw_ipcs)


if __name__ == "__main__":
    main()
