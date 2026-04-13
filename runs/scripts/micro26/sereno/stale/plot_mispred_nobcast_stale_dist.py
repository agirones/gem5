#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) stacked bar chart for the
Sereno/stale variant showing the distribution of dest regs that fell
into the mispredExtraDepsNoBroadcast category, broken down by the
number of stale (misprediction-induced) dependent entries:

  bottom  = mispredExtraDepsNoBroadcast1Stale   (exactly 1 stale dep)
  top     = mispredExtraDepsNoBroadcast2Stale   (exactly 2 stale deps)

Each segment is expressed as a percentage of the total
mispredExtraDepsNoBroadcast count, so the full bar always sums to
≤ 100 % (the remainder are dest regs with 3+ stale deps, not plotted
as a separate segment but accounted for implicitly).

Values are aggregated with simpoint weights; arithmetic mean across
benchmarks is shown at the right.

Output: runs/output/micro26/graphs/mispred_nobcast_stale_dist.tex
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
OUTPUT_TEX = OUTPUT_DIR / "mispred_nobcast_stale_dist.tex"

# Set to a benchmark name (e.g. "628.pop2_s") for per-simpoint debug output.
DEBUG_BM: Optional[str] = None

# ---------------------------------------------------------------------------
# Colors — red family, lighter shades (sub-distribution of NoBroadcast)
# ---------------------------------------------------------------------------
_RED_MED   = ("clrNoBcast1Stale", 255, 152, 150)   # 1 stale dep
_RED_LIGHT = ("clrNoBcast2Stale", 253, 211, 210)   # 2 stale deps

# ---------------------------------------------------------------------------
# Segment descriptors — bottom-to-top stacking order.
# ---------------------------------------------------------------------------
SEGMENTS = [
    ("nobcast_1stale", "1 Stale Dep",  _RED_MED,   None),
    ("nobcast_2stale", "2 Stale Deps", _RED_LIGHT, "dots"),
]

# Stats needed.
STAT_NAMES = [
    "system.cpu.iew.mispredExtraDepsNoBroadcast",
    "system.cpu.iew.mispredExtraDepsNoBroadcast1Stale",
    "system.cpu.iew.mispredExtraDepsNoBroadcast2Stale",
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
# Segment function — maps parsed stats → {segment_key: percentage}
# ---------------------------------------------------------------------------

def _seg_stale(vals: dict[str, float]) -> dict[str, float]:
    total  = vals.get("system.cpu.iew.mispredExtraDepsNoBroadcast")
    s1     = vals.get("system.cpu.iew.mispredExtraDepsNoBroadcast1Stale")
    s2     = vals.get("system.cpu.iew.mispredExtraDepsNoBroadcast2Stale")
    if any(x is None for x in (total, s1, s2)) or total == 0:
        return {}
    return {
        "nobcast_1stale": 100.0 * s1 / total,
        "nobcast_2stale": 100.0 * s2 / total,
    }


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_segments(base_dir: Path) -> dict[str, dict[str, float]]:
    """
    Walk *base_dir*, parse stats, compute percentages, and return
    {benchmark: {segment_key: weighted_mean_percentage}}.
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
                print(f"    {k}: pct={v:.4f}  w*pct={weight * v:.4f}")

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
                    print(f"    {k}: weighted_mean={v:.4f}")
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

    hm_sep = (
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
        r"    ymax            = 100," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    tick align      = outside," "\n"
        r"    ylabel          = {Precise-Path Phantom Deps Distribution (\%)}," "\n"
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
        + hm_sep + "\n"
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
    seg_width = 18

    headers = ["Benchmark".ljust(col_width)]
    for seg_key, seg_label, *_ in SEGMENTS:
        headers.append(seg_label.rjust(seg_width))
    print("\n" + "".join(headers))
    print("-" * (col_width + seg_width * len(SEGMENTS)))

    for bm in all_bms:
        row = [bm.ljust(col_width)]
        for seg_key, *_ in SEGMENTS:
            v = data[bm].get(seg_key, float('nan'))
            row.append(f"{v:{seg_width}.4f}")
        print("".join(row))

    generate_tikz(data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
