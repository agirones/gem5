#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) stacked bar chart showing
the number of broadcast wakeups per approach, subdivided by cause:

  Sereno    : single bar  — broadcastWakeUp
  Sereno-SQ : 3-segment stack
                bottom  = regular broadcast  (broadcastWakeUp
                            - squashInducedBroadcastsWouldBroadcast
                            - squashInducedBroadcastsWouldPrecise)
                middle  = squash-induced, would have broadcast anyway
                            (squashInducedBroadcastsWouldBroadcast)
                top     = squash-induced, would have been precise
                            (squashInducedBroadcastsWouldPrecise)
  Hybrid-WL : 2-segment stack
                bottom  = regular broadcast  (broadcastWakeUp
                            - squashInducedBroadcast)
                top     = squash-induced     (squashInducedBroadcast)

Values are aggregated with simpoint weights:
    result = sum(weight * raw_count) / sum(weight)

Output: runs/output/micro26/graphs/broadcasts_stacked.tex
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path("/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU")

SERENO_DIR    = ROOT / "runs/output/micro26/sereno/ckpt"
SERENOSQ_DIR  = ROOT / "runs/output/micro26/sereno/sqbcast"
HYBRIDWL_DIR  = ROOT / "runs/output/micro26/hybrid-wl/stale"

OUTPUT_DIR = ROOT / "runs/output/micro26/graphs"
OUTPUT_TEX = OUTPUT_DIR / "broadcasts_stacked.tex"

# Y position of the approach labels above the first benchmark's bars.
# None  → auto: total height of the tallest bar in the first benchmark.
# float → use that exact y value (e.g. 2e6).
LABEL_Y = None  # type: Optional[float]

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
# Tableau-10 blue family
_BLUE_DARK  = ("clrBlueDark",   31, 119, 180)   # Sereno / SQ regular
_BLUE_MED   = ("clrBlueMed",   114, 158, 206)   # SQ squash: would-broadcast
_BLUE_LIGHT = ("clrBlueLight", 174, 199, 232)   # SQ squash: would-precise
# Tableau-10 red family
_RED_DARK   = ("clrRedDark",   214,  39,  40)   # Hybrid-WL regular
_RED_MED    = ("clrRedMed",    255, 152, 150)   # Hybrid-WL squash-induced

# ---------------------------------------------------------------------------
# Segment descriptors: (segment_key, label, color_tuple, pattern_or_None)
# Segments listed bottom-to-top in the stacked bar.
# ---------------------------------------------------------------------------
APPROACH_SEGMENTS = {
    "Sereno": [
        ("sereno_regular",       "Broadcast",           _BLUE_DARK,  None),
    ],
    "Sereno-SQ": [
        ("sqbcast_regular",      "Broadcast",           _BLUE_DARK,  None),
        ("sqbcast_would_bc",     "Squash-WouldBC",      _BLUE_MED,   "dots"),
        ("sqbcast_would_pw",     "Squash-WouldPrecise", _BLUE_LIGHT, "north east lines"),
    ],
    "Hybrid-WL": [
        ("hwl_regular",          "Broadcast",           _RED_DARK,   None),
        ("hwl_squash",           "Squash-Induced",      _RED_MED,    "north east lines"),
    ],
}

# Stat names needed per approach directory.
SERENO_STATS = [
    "system.cpu.iew.broadcastWakeUp",
]
SERENOSQ_STATS = [
    "system.cpu.iew.broadcastWakeUp",
    "system.cpu.iew.squashInducedBroadcastsWouldBroadcast",
    "system.cpu.iew.squashInducedBroadcastsWouldPrecise",
]
HYBRIDWL_STATS = [
    "system.cpu.iew.broadcastWakeUp",
    "system.cpu.iew.squashInducedBroadcast",
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
    """
    Parse the final stats dump in *stats_file* and return a dict
    {stat_name: value} for all requested names.  Returns None on I/O error.
    Missing stats are absent from the dict.
    """
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

DEBUG_BM = None   # set to e.g. "600.perlbench_s" for per-simpoint debug output


def collect_segments(
    base_dir: Path,
    stat_names: list[str],
    segment_fn,
) -> dict[str, dict[str, float]]:
    """
    Walk *base_dir*, parse *stat_names* from each stats.txt, apply
    *segment_fn* to get {segment_key: raw_count}, and return
    {benchmark: {segment_key: weighted_sum}}.

    Aggregation: sum(weight * raw_count) / sum(weight)
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
        vals = parse_stats(sf, stat_names)
        if vals is None:
            print(f"  WARNING: I/O error reading {sf}")
            continue
        segs = segment_fn(vals)
        if not segs:
            print(f"  WARNING: segment_fn returned empty for {sf}")
            continue
        bm     = extract_benchmark(sf)
        weight = extract_weight(sf)

        if DEBUG_BM and bm == DEBUG_BM:
            print(f"  [DEBUG {bm}] simpoint={sf.parent.parent.name}  weight={weight:.6f}")
            for k, raw in segs.items():
                print(f"    {k}: raw={raw:.0f}  w*raw={weight*raw:.2f}")

        for key, raw in segs.items():
            weighted[bm][key] += weight * raw
        wsum[bm] += weight

    result: dict[str, dict[str, float]] = {}
    for bm, seg_dict in weighted.items():
        w = wsum[bm]
        if w > 0:
            result[bm] = {k: v / w for k, v in seg_dict.items()}
            if DEBUG_BM and bm == DEBUG_BM:
                print(f"  [DEBUG {bm}] FINAL  weight_sum={w:.6f}")
                for k, v in result[bm].items():
                    print(f"    {k}: weighted_sum={v:.2f}")
    return result


# Segment functions — map parsed stat values → {segment_key: raw_count}

def _seg_sereno(vals):
    bc = vals.get("system.cpu.iew.broadcastWakeUp")
    return {"sereno_regular": bc} if bc is not None else {}


def _seg_serenosq(vals):
    bc  = vals.get("system.cpu.iew.broadcastWakeUp")
    wbc = vals.get("system.cpu.iew.squashInducedBroadcastsWouldBroadcast")
    wpw = vals.get("system.cpu.iew.squashInducedBroadcastsWouldPrecise")
    if any(x is None for x in (bc, wbc, wpw)):
        return {}
    return {
        "sqbcast_regular":  max(0.0, bc - wbc - wpw),
        "sqbcast_would_bc": wbc,
        "sqbcast_would_pw": wpw,
    }


def _seg_hybridwl(vals):
    bc  = vals.get("system.cpu.iew.broadcastWakeUp")
    sq  = vals.get("system.cpu.iew.squashInducedBroadcast")
    if bc is None or sq is None:
        return {}
    return {
        "hwl_regular": max(0.0, bc - sq),
        "hwl_squash":  sq,
    }


def clean_label(benchmark: str) -> str:
    label = re.sub(r'^\d+\.', '', benchmark)
    label = re.sub(r'_s$', '', label)
    return label


# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------

def _escape_latex(s: str) -> str:
    return s.replace('_', r'\_').replace('%', r'\%').replace('&', r'\&')


def generate_tikz(
    all_data: dict[str, dict[str, dict[str, float]]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    approach_names = list(APPROACH_SEGMENTS.keys())
    AP_SFX = {"Sereno": "S", "Sereno-SQ": "SQ", "Hybrid-WL": "HWL"}

    # Common benchmark set.
    common_bms: set[str] = None  # type: ignore
    for name in approach_names:
        bms = set(all_data.get(name, {}).keys())
        common_bms = bms if common_bms is None else common_bms & bms
    if not common_bms:
        print("ERROR: no benchmarks common to all approaches.")
        return
    all_benchmarks = sorted(common_bms)

    # Arithmetic mean per approach per segment.
    mean_segs: dict[str, dict[str, float]] = {}
    for name in approach_names:
        mean_segs[name] = {}
        for seg_key, *_ in APPROACH_SEGMENTS[name]:
            vals = [all_data[name][bm].get(seg_key, 0.0) for bm in all_benchmarks]
            mean_segs[name][seg_key] = sum(vals) / len(vals) if vals else 0.0

    def xc(bm: str, ap: str) -> str:
        return f"{bm}_{AP_SFX[ap]}"

    def xc_hm(ap: str) -> str:
        return f"HM_{AP_SFX[ap]}"

    # Symbolic x-coord list.
    sym_list: list[str] = []
    for i, bm in enumerate(all_benchmarks):
        for ap in approach_names:
            sym_list.append(xc(bm, ap))
        sym_list.append(f"sp{i+1}")
    sym_list.append("spMn")
    for ap in approach_names:
        sym_list.append(xc_hm(ap))
    sym_coords = ", ".join(sym_list)

    # xtick = middle approach (Sereno-SQ) for centred labels.
    mid_ap = approach_names[1]
    xtick_coords = [xc(bm, mid_ap) for bm in all_benchmarks] + [xc_hm(mid_ap)]
    xtick       = ", ".join(xtick_coords)
    xticklabels = ", ".join([clean_label(bm) for bm in all_benchmarks] + [r"\textbf{Mean}"])

    # Color definitions.
    seen_colors: set[str] = set()
    color_defs = ""
    for segs_def in APPROACH_SEGMENTS.values():
        for _, _, color_tuple, _ in segs_def:
            cname, r, g, b = color_tuple
            if cname not in seen_colors:
                seen_colors.add(cname)
                color_defs += f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    # addplot_specs: (legend_label, color_tuple, pattern, {ap_name: seg_key|None})
    # Order determines both stacking (bottom→top) and legend order.
    addplot_specs = [
        ("Broadcast",          _BLUE_DARK,  None,
         {"Sereno": "sereno_regular", "Sereno-SQ": "sqbcast_regular", "Hybrid-WL": None}),
        ("Squash-WouldBC",     _BLUE_MED,   "dots",
         {"Sereno": None, "Sereno-SQ": "sqbcast_would_bc", "Hybrid-WL": None}),
        ("Squash-WouldPrecise",_BLUE_LIGHT, "north east lines",
         {"Sereno": None, "Sereno-SQ": "sqbcast_would_pw", "Hybrid-WL": None}),
        ("Broadcast",          _RED_DARK,   None,
         {"Sereno": None, "Sereno-SQ": None, "Hybrid-WL": "hwl_regular"}),
        ("Squash-Induced",     _RED_MED,    "north east lines",
         {"Sereno": None, "Sereno-SQ": None, "Hybrid-WL": "hwl_squash"}),
    ]

    def bm_val(ap: str, seg_key: Optional[str], bm: str) -> float:
        if seg_key is None:
            return 0.0
        return all_data.get(ap, {}).get(bm, {}).get(seg_key, 0.0)

    def hm_val(ap: str, seg_key: Optional[str]) -> float:
        if seg_key is None:
            return 0.0
        return mean_segs.get(ap, {}).get(seg_key, 0.0)

    # Legend deduplication: same (label, color_name) → one entry.
    seen_legend: set[tuple] = set()
    addplot_blocks: list[str] = []
    for leg_label, color_tuple, pattern, ap_segs in addplot_specs:
        cname = color_tuple[0]
        postaction = (
            f"        postaction={{pattern={pattern}, draw=black}},\n"
            if pattern else ""
        )

        coord_lines: list[str] = []
        for i, bm in enumerate(all_benchmarks):
            for ap in approach_names:
                v = bm_val(ap, ap_segs.get(ap), bm)
                coord_lines.append(f"({xc(bm, ap)}, {v:.8f})")
            coord_lines.append(f"(sp{i+1}, 0)")
        coord_lines.append("(spMn, 0)")
        for ap in approach_names:
            v = hm_val(ap, ap_segs.get(ap))
            coord_lines.append(f"({xc_hm(ap)}, {v:.8f})")

        coord_body = "\n        ".join(coord_lines)
        escaped_label = _escape_latex(leg_label)

        dedup_key = (leg_label, cname)
        legend_entry = (
            f"    \\addlegendentry{{{escaped_label}}}"
            if dedup_key not in seen_legend
            else "    % (legend entry suppressed – duplicate)"
        )
        seen_legend.add(dedup_key)

        addplot_blocks.append(
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw={cname}!70!black,\n"
            f"        line width=0.4pt,\n"
            + postaction +
            f"    ] coordinates {{\n"
            f"        {coord_body}\n"
            f"    }};\n"
            + legend_entry
        )

    addplot_str = "\n\n".join(addplot_blocks)

    # Approach labels above the first benchmark's bars.
    first_bm = all_benchmarks[0]
    if LABEL_Y is not None:
        _label_y = LABEL_Y
    else:
        _label_y = max(
            sum(all_data[ap][first_bm].get(sk, 0.0) for sk, *_ in APPROACH_SEGMENTS[ap])
            for ap in approach_names
        )
    ap_labels_code = "\n".join(
        f"    \\node[rotate=90, anchor=west, font=\\tiny, inner sep=1pt]\n"
        f"        at (axis cs:{xc(first_bm, ap)}, {_label_y:.4f}) {{{ap}}};"
        for ap in approach_names
    )

    # Dashed separator before the Mean group.
    hm_sep = (
        f"    \\begin{{pgfonlayer}}{{background}}\n"
        f"        \\fill[gray!15] ([xshift=-4.5pt]{{axis cs:{xc_hm(approach_names[0])},\\pgfkeysvalueof{{/pgfplots/ymin}}}}) rectangle (rel axis cs:1,1);\n"
        f"    \\end{{pgfonlayer}}"
    )
    after_end_code = ap_labels_code + "\n" + hm_sep

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
        r"    bar width       = 4pt," "\n"
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
        r"    tick align        = outside," "\n"
        r"    ylabel          = {Broadcasts}," "\n"
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
    configs = [
        ("Sereno",    SERENO_DIR,   SERENO_STATS,   _seg_sereno),
        ("Sereno-SQ", SERENOSQ_DIR, SERENOSQ_STATS, _seg_serenosq),
        ("Hybrid-WL", HYBRIDWL_DIR, HYBRIDWL_STATS, _seg_hybridwl),
    ]

    all_data: dict[str, dict[str, dict[str, float]]] = {}
    for name, base_dir, stat_names, seg_fn in configs:
        if not base_dir.exists():
            print(f"SKIP {name}: directory not found ({base_dir})")
            continue
        print(f"Collecting segments for {name} …")
        data = collect_segments(base_dir, stat_names, seg_fn)
        print(f"  → {len(data)} benchmarks")
        all_data[name] = data

    if not all_data:
        print("No data found – nothing to plot.")
        return

    # Summary table.
    all_bms = sorted(set().union(*[d.keys() for d in all_data.values()]))
    col_width = max(len(b) for b in all_bms) + 2

    headers = ["Benchmark".ljust(col_width)]
    for ap in APPROACH_SEGMENTS:
        for seg_key, label, *_ in APPROACH_SEGMENTS[ap]:
            headers.append(f"{ap}/{label}".rjust(22))
    print("\n" + "".join(headers))
    print("-" * (col_width + 22 * sum(len(s) for s in APPROACH_SEGMENTS)))

    for bm in all_bms:
        row = [bm.ljust(col_width)]
        for ap in APPROACH_SEGMENTS:
            for seg_key, *_ in APPROACH_SEGMENTS[ap]:
                v = all_data.get(ap, {}).get(bm, {}).get(seg_key, float('nan'))
                row.append(f"{v:22.6f}")
        print("".join(row))

    generate_tikz(all_data, OUTPUT_TEX)


if __name__ == "__main__":
    main()
