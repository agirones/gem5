#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) stacked bar chart for the
Sereno/stale variant showing, per committed instruction, how many
destination registers had extra dependencies caused by branch
mispredictions, classified into three groups:

  bottom  = mispredExtraDepsWouldBroadcast
            Stale extra deps present, but true deps (numRegDependents)
            already exceeded broadcastThreshold → broadcast would have
            happened anyway.

  middle  = mispredExtraDepsBroadcastInduced
            Stale extra deps pushed the registered count over
            broadcastThreshold while true deps were below it → the
            broadcast was induced solely by the misprediction.

  top     = mispredExtraDepsNoBroadcast
            Stale extra deps present, but even with them the registered
            count stayed at or below broadcastThreshold → precise wakeup
            was taken despite the extra stale entries.

Values are aggregated with simpoint weights and normalised per committed
instruction (system.cpu.commitStats0.numInsts).

Output: runs/output/micro26/graphs/mispred_extra_deps_stale.tex
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path("/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU")

STALE_DIR  = ROOT / "runs/output/micro26/sereno/stale"

OUTPUT_DIR = ROOT / "runs/output/micro26/graphs"
OUTPUT_TEX = OUTPUT_DIR / "mispred_extra_deps_stale.tex"

# Set to a benchmark name (e.g. "628.pop2_s") for per-simpoint debug output.
DEBUG_BM: Optional[str] = None

# ---------------------------------------------------------------------------
# Colors — red family (stale variant uses red in this context)
# ---------------------------------------------------------------------------
_RED_DARK  = ("clrMispredWouldBcast",   214,  39,  40)   # would broadcast anyway
_RED_MED   = ("clrMispredInduced",      255, 152, 150)   # broadcast induced by mispred
_RED_LIGHT = ("clrMispredNoBcast",      253, 211, 210)   # no broadcast despite extra deps

# ---------------------------------------------------------------------------
# Segment descriptors — bottom-to-top stacking order.
# ---------------------------------------------------------------------------
SEGMENTS = [
    ("mispred_would_bcast",   "WouldBroadcast",    _RED_DARK,  None),
    ("mispred_induced",       "BcastInduced",      _RED_MED,   "dots"),
    ("mispred_no_bcast",      "NoBroadcast",       _RED_LIGHT, "north east lines"),
]

# Stats needed.
STAT_NAMES = [
    "system.cpu.iew.mispredExtraDepsWouldBroadcast",
    "system.cpu.iew.mispredExtraDepsBroadcastInduced",
    "system.cpu.iew.mispredExtraDepsNoBroadcast",
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
    """Parse the final stats dump and return {stat_name: value}."""
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
# Segment function — maps parsed stats → {segment_key: count_per_instr}
# ---------------------------------------------------------------------------

def _seg_stale(vals: dict[str, float]) -> dict[str, float]:
    would    = vals.get("system.cpu.iew.mispredExtraDepsWouldBroadcast")
    induced  = vals.get("system.cpu.iew.mispredExtraDepsBroadcastInduced")
    no_bcast = vals.get("system.cpu.iew.mispredExtraDepsNoBroadcast")
    if any(x is None for x in (would, induced, no_bcast)):
        return {}
    total = would + induced + no_bcast
    if total == 0:
        return {}
    return {
        "mispred_would_bcast": 100.0 * would    / total,
        "mispred_induced":     100.0 * induced  / total,
        "mispred_no_bcast":    100.0 * no_bcast / total,
    }


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_segments(base_dir: Path) -> dict[str, dict[str, float]]:
    """
    Walk *base_dir*, parse stats, normalise per committed instruction,
    and return {benchmark: {segment_key: weighted_mean}}.
    """
    stats_files = sorted(
        f for f in base_dir.glob("**/stats.txt")
        if "sensibility_analysis" not in f.parts
    )
    if not stats_files:
        print(f"  WARNING: no stats.txt found under {base_dir}")
        return {}

    weighted: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    wsum:     dict[str, float] = defaultdict(float)

    for sf in stats_files:
        vals = parse_stats(sf, STAT_NAMES)
        if vals is None:
            print(f"  WARNING: I/O error reading {sf}")
            continue
        segs = _seg_stale(vals)
        if not segs:
            print(f"  WARNING: missing stats in {sf}")
            continue
        bm     = extract_benchmark(sf)
        weight = extract_weight(sf)

        if DEBUG_BM and bm == DEBUG_BM:
            simpoint = sf.parent.parent.name
            print(f"  [DEBUG] [{bm}]  simpoint={simpoint}  weight={weight:.6f}")
            for k, v in segs.items():
                print(f"    {k}: rate={v:.8f}  w*rate={weight * v:.8f}")

        for key, v in segs.items():
            weighted[bm][key] += weight * v
        wsum[bm] += weight

    result: dict[str, dict[str, float]] = {}
    for bm, seg_dict in weighted.items():
        w = wsum[bm]
        if w > 0:
            result[bm] = {k: v / w for k, v in seg_dict.items()}
            if DEBUG_BM and bm == DEBUG_BM:
                print(f"  [DEBUG] [{bm}]  FINAL  weight_sum={w:.6f}")
                for k, v in result[bm].items():
                    print(f"    {k}: weighted_mean={v:.8f}")
    return result


def clean_label(benchmark: str) -> str:
    label = re.sub(r'^\d+\.', '', benchmark)
    label = re.sub(r'_s$', '', label)
    return label


# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------

def _escape_latex(s: str) -> str:
    return s.replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')


def generate_tikz(data: dict[str, dict[str, float]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_benchmarks = sorted(data.keys())
    if not all_benchmarks:
        print("ERROR: no benchmark data to plot.")
        return

    # Arithmetic mean per segment for the "Mean" group.
    mean_segs: dict[str, float] = {}
    for seg_key, *_ in SEGMENTS:
        vals = [data[bm].get(seg_key, 0.0) for bm in all_benchmarks]
        mean_segs[seg_key] = sum(vals) / len(vals) if vals else 0.0

    # Symbolic x-coords: per-benchmark bar, then mean bar.
    sym_list: list[str] = list(all_benchmarks) + ["Mean"]
    sym_coords = ", ".join(sym_list)

    xtick       = ", ".join(all_benchmarks + ["Mean"])
    xticklabels = ", ".join(
        [clean_label(bm) for bm in all_benchmarks] + [r"\textbf{Mean}"]
    )

    # Color definitions.
    seen_colors: set[str] = set()
    color_defs = ""
    for _, _, color_tuple, _ in SEGMENTS:
        cname, r, g, b = color_tuple
        if cname not in seen_colors:
            seen_colors.add(cname)
            color_defs += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    # Approach label above first bar.
    first_bm = all_benchmarks[0]
    label_y = sum(data[first_bm].get(sk, 0.0) for sk, *_ in SEGMENTS)

    after_end_code = (
        f"    \\begin{{pgfonlayer}}{{background}}\n"
        f"        \\fill[gray!15] ([xshift=-4.5pt]{{axis cs:Mean,\\pgfkeysvalueof{{/pgfplots/ymin}}}}) rectangle (rel axis cs:1,1);\n"
        f"    \\end{{pgfonlayer}}"
    )

    # One addplot block per segment.
    addplot_blocks: list[str] = []
    for seg_key, leg_label, color_tuple, pattern in SEGMENTS:
        cname = color_tuple[0]
        postaction = (
            f"        postaction={{pattern={pattern}, draw=black}},\n"
            if pattern else ""
        )

        coord_lines: list[str] = []
        for bm in all_benchmarks:
            v = data[bm].get(seg_key, 0.0)
            coord_lines.append(f"({bm}, {v:.8f})")
        coord_lines.append(f"(Mean, {mean_segs.get(seg_key, 0.0):.8f})")

        coord_body = "\n        ".join(coord_lines)
        escaped_label = _escape_latex(leg_label)

        addplot_blocks.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw={cname}!70!black,\n"
            f"        line width=0.4pt,\n"
            + postaction +
            f"    ] coordinates {{\n"
            f"        {coord_body}\n"
            f"    }};\n"
            f"    \\addlegendentry{{{escaped_label}}}"
        )

    addplot_str = "\n\n".join(addplot_blocks)

    tex = (
        r"\documentclass[tikz]{standalone}" "\n"
        r"\usepackage{pgfplots}" "\n"
        r"\usetikzlibrary{patterns}" "\n"
        r"\pgfplotsset{compat=1.18}" "\n"
        "\n"
        r"\pgfdeclarelayer{background}" "\n"
        r"\pgfsetlayers{background,main}" "\n"
        "\n"
        + color_defs +
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
        r"    bar width       = 6pt," "\n"
        r"    width           = 18cm," "\n"
        r"    height          = 6cm," "\n"
        r"    enlarge x limits= 0.02," "\n"
        r"    clip            = false," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        f"    xtick           = {{{xtick}}},\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    x tick label style = {rotate=90, anchor=east, font=\scriptsize}," "\n"
        r"    ymin            = 0," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    tick align      = outside," "\n"
        r"    ylabel          = {Instruction with Misprediction Dependences}," "\n"
        r"    ylabel style    = {font=\small}," "\n"
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
        + after_end_code + "\n"
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
    if not STALE_DIR.exists():
        print(f"ERROR: directory not found: {STALE_DIR}")
        return

    print("Collecting segments for stale …")
    data = collect_segments(STALE_DIR)
    print(f"  → {len(data)} benchmarks")

    if not data:
        print("No data found – nothing to plot.")
        return

    # Summary table.
    all_bms = sorted(data.keys())
    col_width = max((len(b) for b in all_bms), default=20) + 2
    seg_width = 28

    headers = ["Benchmark".ljust(col_width)]
    for seg_key, seg_label, *_ in SEGMENTS:
        headers.append(seg_label.rjust(seg_width))
    print("\n" + "".join(headers))
    print("-" * (col_width + seg_width * len(SEGMENTS)))

    for bm in all_bms:
        row = [bm.ljust(col_width)]
        for seg_key, *_ in SEGMENTS:
            v = data[bm].get(seg_key, float('nan'))
            row.append(f"{v:{seg_width}.8f}")
        print("".join(row))

    generate_tikz(data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
