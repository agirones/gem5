#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) grouped stacked bar chart
showing "Broadcast Port Utilization" per benchmark for three configurations.

For each benchmark on the X-axis, three side-by-side stacked bars are shown
(left to right: CAM-based, Hybrid-1D, Hybrid-2D). Each bar is stacked with
13 categories representing 0 … 12 broadcast ports active in that cycle.
The rightmost group gives the arithmetic mean across all benchmarks.

Data sources
------------
  CAM-based : real per-benchmark data read from the baseline simulation
              runs/output/micro26/baseline/12B_-1P/width8/{bm}/{sp}/m5out/stats.txt
              stat: system.cpu.iew.broadcastsPerWakeUpCycle::{0..12}

  Hybrid-1D : per-benchmark projection derived by applying the element-wise
              ratio _REP_H1D[i] / _REP_CAM[i] to each benchmark's measured
              CAM distribution, then re-normalising.

  Hybrid-2D : same derivation using _REP_H2D[i] / _REP_CAM[i].

  Replace _REP_H1D / _REP_H2D with actual simulation data if available.

Output: runs/output/micro26/baseline/12B_-1P/graphs/broadcast_port_utilization.tex
"""

import re
from collections import defaultdict
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[5]          # .../gem5-NTNU/
CAM_DIR   = ROOT / "runs/output/micro26/baseline/12B_-1P/width8"
OUTPUT_TEX = (
    ROOT
    / "runs/output/micro26/baseline/12B_-1P/graphs"
    / "broadcast_port_utilization.tex"
)

NUM_CATS  = 13      # broadcast-port buckets 0 … 12
STAT_BASE = "system.cpu.iew.broadcastsPerWakeUpCycleExcept0"
STAT_KEYS = [f"{STAT_BASE}::{i}" for i in range(NUM_CATS)]

STAT_BASE_EX01  = "system.cpu.iew.broadcastsPerWakeUpCycleExcept01"
STAT_KEYS_EX01  = [f"{STAT_BASE_EX01}::{i}" for i in range(NUM_CATS)]

STAT_BASE_EX012 = "system.cpu.iew.broadcastsPerWakeUpCycleExcept012"
STAT_KEYS_EX012 = [f"{STAT_BASE_EX012}::{i}" for i in range(NUM_CATS)]

# Single set covering all three histograms — O(1) exact lookup
STAT_KEYS_SET = set(STAT_KEYS) | set(STAT_KEYS_EX01) | set(STAT_KEYS_EX012)

# ------------------------------------------------------------------ #
# Representative distributions used as scaling profiles               #
# (global, in % of cycles; all must sum to 100)                       #
# ------------------------------------------------------------------ #
_REP_CAM = [38.0, 20.0, 15.0, 10.0, 6.0, 3.0, 2.0, 1.0, 2.0, 1.5,  0.8, 0.5, 0.2 ]
_REP_H1D = [55.0, 25.0, 10.0,  5.0, 2.0, 1.0, 0.6, 0.4, 0.4, 0.3,  0.15, 0.10, 0.05]
_REP_H2D = [85.0, 12.0,  1.5,  0.8, 0.4, 0.15, 0.07, 0.03, 0.02, 0.01, 0.01, 0.01, 0.0 ]

# ------------------------------------------------------------------ #
# Colour palette                                                       #
#  cat0   : light gray + crosshatch-dots  →  "idle logic"            #
#  cat1   : clrSereno (tableau blue)      →  "1 port is sufficient"  #
#  cat2-12: YlGnBu ColorBrewer sequence (light yellow → dark navy)   #
# ------------------------------------------------------------------ #
_CAT_RGB = [
    (166, 206, 227),   # cat0: Light Blue
    ( 31, 120, 180),   # cat1: Dark Blue
    (178, 223, 138),   # cat2: Light Green
    ( 51, 160, 44),    # cat3: Dark Green
    (251, 154, 153),   # cat4: Light Red
    (227,  26,  28),   # cat5: Dark Red
    (253, 191, 111),   # cat6: Light Orange
    (255, 127,   0),   # cat7: Dark Orange
    (202, 178, 214),   # cat8: Light Purple
    (106,  61, 154),   # cat9: Dark Purple
    (255, 255, 153),   # cat10: Pale Yellow
    (177,  89,  40),   # cat11: Brown
    ( 80,  80,  80),   # cat12: Dark Slate
]
_PATTERNS = [None] + [None] * 12
_PAT_COLS = ["gray!60"]         + [None] * 12

CONFIGS      = ["CAM", "H1D", "H2D"]
CONFIG_DISP  = {"CAM": "CAM-based", "H1D": "Hybrid-1D", "H2D": "Hybrid-2D"}

# ------------------------------------------------------------------ #
# Stats parsing                                                        #
# ------------------------------------------------------------------ #

def extract_weight(path):
    m = re.search(r'weight_([0-9]+\.[0-9]+)', str(path))
    return float(m.group(1)) if m else 1.0


def parse_stats(stats_file):
    """Return the last-dump values for STAT_KEYS from a stats.txt file."""
    in_dump  = False
    current  = {}
    last     = {}
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


def collect_cam_data(base_dir):
    """Return {benchmark: {stat_key: weighted_sum}} — raw weighted sums over simpoints."""
    if not base_dir.exists():
        print(f"ERROR: CAM data directory not found: {base_dir}")
        return {}
    stats_files = sorted(base_dir.glob("**/stats.txt"))
    if not stats_files:
        print(f"WARNING: no stats.txt files under {base_dir}")
        return {}

    weighted = defaultdict(lambda: defaultdict(float))

    for sf in stats_files:
        benchmark = sf.parent.parent.parent.name
        weight    = extract_weight(sf.parent.parent.name)
        vals      = parse_stats(sf)
        if not vals:
            print(f"  WARNING: no broadcastsPerWakeUpCycle stats in {sf}")
            continue

        for key in STAT_KEYS + STAT_KEYS_EX01 + STAT_KEYS_EX012:
            if key in vals:
                weighted[benchmark][key] += weight * vals[key]

    return {bm: dict(d) for bm, d in weighted.items()}


# ------------------------------------------------------------------ #
# Distribution helpers                                                 #
# ------------------------------------------------------------------ #

def to_percentages(vals, keys=None):
    """Convert raw weighted counts to a 13-element percentage list."""
    if keys is None:
        keys = STAT_KEYS
    counts = [vals.get(k, 0.0) for k in keys]
    total  = sum(counts)
    if total <= 0:
        return [0.0] * NUM_CATS
    return [100.0 * c / total for c in counts]


def scale_distribution(cam_pct, rep_cam, rep_target):
    """
    Derive a per-benchmark target distribution.

    Apply the global element-wise ratio rep_target[i] / rep_cam[i] to
    cam_pct[i], then re-normalise to 100 %.
    This preserves per-benchmark character while following the global
    reduction profile of the Hybrid proposals.
    """
    scaled = []
    for i in range(NUM_CATS):
        if rep_cam[i] > 0:
            scaled.append(cam_pct[i] * (rep_target[i] / rep_cam[i]))
        else:
            scaled.append(0.0)
    total = sum(scaled)
    if total > 0:
        return [s * 100.0 / total for s in scaled]
    return [0.0] * NUM_CATS


def clean_label(name):
    label = re.sub(r'^\d+\.', '', name)
    label = re.sub(r'_s$', '', label)
    return label


# ------------------------------------------------------------------ #
# LaTeX / pgfplots generation                                          #
# ------------------------------------------------------------------ #

def _define_colors():
    lines = [
        f"\\definecolor{{clrCat{i}}}{{RGB}}{{{r},{g},{b}}}"
        for i, (r, g, b) in enumerate(_CAT_RGB)
    ]
    return "\n".join(lines) + "\n"


def generate_tikz(cam_raw, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    benchmarks = sorted(cam_raw.keys())
    if not benchmarks:
        print("No benchmark data – nothing to plot.")
        return

    # ---- per-benchmark distributions for all 3 configs ---------------
    pct = {}   # pct[bm][cfg] = list[float] (13 percentages summing to 100)
    for bm in benchmarks:
        pct[bm] = {
            "CAM": to_percentages(cam_raw[bm], STAT_KEYS),
            "H1D": to_percentages(cam_raw[bm], STAT_KEYS_EX01),
            "H2D": to_percentages(cam_raw[bm], STAT_KEYS_EX012),
        }

    # ---- weighted arithmetic mean across benchmarks (weight = total events per bm per cfg)
    stat_keys_for_cfg = {"CAM": STAT_KEYS, "H1D": STAT_KEYS_EX01, "H2D": STAT_KEYS_EX012}
    mean_pct = {}
    for cfg in CONFIGS:
        keys        = stat_keys_for_cfg[cfg]
        bm_totals   = {bm: sum(cam_raw[bm].get(k, 0.0) for k in keys) for bm in benchmarks}
        grand_total = sum(bm_totals.values())
        bm_weights  = {bm: bm_totals[bm] / grand_total for bm in benchmarks} if grand_total > 0 \
                      else {bm: 1.0 / len(benchmarks) for bm in benchmarks}
        mean_pct[cfg] = [
            sum(bm_weights[bm] * pct[bm][cfg][i] for bm in benchmarks)
            for i in range(NUM_CATS)
        ]

    # ---- symbolic x-coordinates (sub-coordinate trick) ----------------
    # Each benchmark group: {bm}_CAM, {bm}_H1D, {bm}_H2D
    # A spacer coord (sp0, sp1, …) is inserted between every consecutive
    # group to create a wider visual gap while keeping intra-group bars
    # tightly packed.  The spacer before Mean replaces the dashed line.
    # xtick is positioned at the centre bar (H1D) of each group.
    all_x    = []
    spacers  = []
    xtick    = []
    xlabels  = []
    for j, bm in enumerate(benchmarks):
        if j > 0:
            sp = f"sp{j}"
            all_x.append(sp)
            spacers.append(sp)
        all_x.extend([f"{bm}_CAM", f"{bm}_H1D", f"{bm}_H2D"])
        xtick.append(f"{bm}_H1D")
        xlabels.append(clean_label(bm))
    # Spacer before Mean group
    sp_mean = "spMn"
    all_x.append(sp_mean)
    spacers.append(sp_mean)
    all_x.extend(["Mn_CAM", "Mn_H1D", "Mn_H2D"])
    xtick.append("Mn_H1D")
    xlabels.append(r"\textbf{Mean}")

    sym_coords      = ", ".join(all_x)
    xtick_str       = ", ".join(xtick)
    xticklabels_str = ", ".join(xlabels)

    # ---- addplot blocks: one per category (0 … 12) --------------------
    # Each block covers ALL (benchmark × config) coordinates so that
    # pgfplots stacks only within a unique x-label (i.e., per config
    # per benchmark) and not across configs.
    addplot_blocks = []
    for i in range(NUM_CATS):
        cname  = f"clrCat{i}"
        pat    = _PATTERNS[i]
        patcol = _PAT_COLS[i]

        coords = []
        for j, bm in enumerate(benchmarks):
            if j > 0:
                coords.append(f"(sp{j}, 0.0000)")
            for cfg in CONFIGS:
                coords.append(f"({bm}_{cfg}, {pct[bm][cfg][i]:.4f})")
        coords.append("(spMn, 0.0000)")
        for cfg in CONFIGS:
            coords.append(f"(Mn_{cfg}, {mean_pct[cfg][i]:.4f})")
        coord_body = "\n        ".join(coords)

        postaction = (
            f",\n        postaction={{pattern={pat}, pattern color={patcol}}}"
            if pat else ""
        )
        block = (
            f"    \\addplot[\n"
            f"        fill={cname},\n"
            f"        draw=black!60,\n"
            f"        line width=0.3pt{postaction},\n"
            f"    ] coordinates {{\n"
            f"        {coord_body}\n"
            f"    }};\n"
        )
        if i == 0:
            block += "    \\addlegendentry{0}\n"
        elif i == 1:
            block += "    \\addlegendentry{1}\n"
        else:
            block += f"    \\addlegendentry{{{i}}}\n"
        addplot_blocks.append(block)

    addplot_str = "\n".join(addplot_blocks)

    # Grey shadow background for the Mean group (replaces dashed separator).
    mean_sep = (
        "    \\begin{pgfonlayer}{background}\n"
        "        \\fill[gray!60] ([xshift=-4.5pt]{axis cs:Mn_CAM,\\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);\n"
        "    \\end{pgfonlayer}\n"
    )

    first_bm = benchmarks[0]
    config_labels_str = (
        f"    % --- config labels on first group bars ---\n"
        f"    \\node[rotate=90, anchor=west, font=\\tiny, inner sep=1pt]\n"
        f"        at (axis cs:{first_bm}_CAM, 102) {{CAM-Based}};\n"
        f"    \\node[rotate=90, anchor=west, font=\\tiny, inner sep=1pt]\n"
        f"        at (axis cs:{first_bm}_H1D, 102) {{Hybrid-1D}};\n"
        f"    \\node[rotate=90, anchor=west, font=\\tiny, inner sep=1pt]\n"
        f"        at (axis cs:{first_bm}_H2D, 102) {{Hybrid-2D}};\n"
    )

    # ---- chart width: scale with number of benchmarks + spacers ------
    # Total x-slots = 3*n (bars) + (n-1+1) spacers + 3 (mean) = 4n + 3
    n = len(benchmarks)
    chart_width_cm = max(12.0, (4 * n + 4) * 0.18)

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
        r"    bar width       = 4.5pt," "\n"
        r"    width           = 1.3\textwidth, height=4cm, scale only axis," "\n"
        r"    enlarge x limits= 0.03," "\n"
        r"    clip             = false," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        f"    xtick             = {{{xtick_str}}},\n"
        f"    xticklabels       = {{{xticklabels_str}}},\n"
        f"    minor xtick       = {{{xtick_str}}},\n"
        f"    minor x tick num  = 0," "\n"
        f"    tick align        = outside," "\n"
        f"    minor tick length = 3pt," "\n"
        r"    x tick label style = {rotate=90, anchor=east}," "\n"
        r"    ymin            = 0," "\n"
        r"    ymax            = 100," "\n"
        r"    ytick           = {0, 20, 40, 60, 80, 100}," "\n"
        r"    yticklabel      = {\pgfmathprintnumber{\tick}\%}," "\n"
        r"    ylabel          = {Percentage of Cycles}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    legend style    = {" "\n"
        r"        at={(0.5,1.05)}, anchor=south," "\n"
        r"        font=\scriptsize," "\n"
        r"        cells={anchor=west}," "\n"
        r"        draw=none," "\n"
        r"        /tikz/every even column/.append style={column sep=6pt}," "\n"
        r"    }," "\n"
        r"    legend columns  = -1," "\n"
        r"    tick label style= {font=\scriptsize}," "\n"
        r"    after end axis/.code={" "\n"
        + mean_sep
        + config_labels_str +
        r"    }," "\n"
        r"]" "\n"
        "\n"
        + addplot_str + "\n"
        r"\end{axis}" "\n"
        r"\end{tikzpicture}" "\n"
        r"\end{document}" "\n"
    )

    with open(output_path, "w") as f:
        f.write(tex)
    print(f"Saved: {output_path}")


# ------------------------------------------------------------------ #
# Main                                                                 #
# ------------------------------------------------------------------ #

def main():
    print(f"Collecting broadcastsPerWakeUpCycle stats from:\n  {CAM_DIR}\n")
    cam_raw = collect_cam_data(CAM_DIR)
    if not cam_raw:
        print("No data found – nothing to plot.")
        return

    benchmarks = sorted(cam_raw.keys())
    print(f"Found {len(benchmarks)} benchmarks.\n")

    # Print summary table
    hdr = (
        f"{'Benchmark':<28}"
        + "".join(f"{f'k={i}':>8}" for i in range(NUM_CATS))
    )
    print(hdr)
    print("-" * len(hdr))

    cam_pcts_all = []
    for bm in benchmarks:
        cam_pct = to_percentages(cam_raw[bm])
        cam_pcts_all.append(cam_pct)
        row = f"{bm:<28}" + "".join(f"{v:>7.2f}%" for v in cam_pct)
        print(row)

    bm_totals_cam   = [sum(cam_raw[bm].get(k, 0.0) for k in STAT_KEYS) for bm in benchmarks]
    grand_total_cam = sum(bm_totals_cam)
    bm_weights_cam  = [t / grand_total_cam for t in bm_totals_cam] if grand_total_cam > 0 \
                      else [1.0 / len(benchmarks)] * len(benchmarks)
    means = [
        sum(bm_weights_cam[j] * cam_pcts_all[j][i] for j in range(len(benchmarks)))
        for i in range(NUM_CATS)
    ]
    print("-" * len(hdr))
    print(f"{'Mean (CAM)':<28}" + "".join(f"{v:>7.2f}%" for v in means))
    print()

    # ---- Except01 table -------------------------------------------
    print(f"\n[broadcastsPerWakeUpCycleExcept01]")
    print(hdr)
    print("-" * len(hdr))
    ex01_pcts_all = []
    for bm in benchmarks:
        ex01_pct = to_percentages(cam_raw[bm], STAT_KEYS_EX01)
        ex01_pcts_all.append(ex01_pct)
        row = f"{bm:<28}" + "".join(f"{v:>7.2f}%" for v in ex01_pct)
        print(row)
    bm_totals_ex01   = [sum(cam_raw[bm].get(k, 0.0) for k in STAT_KEYS_EX01) for bm in benchmarks]
    grand_total_ex01 = sum(bm_totals_ex01)
    bm_weights_ex01  = [t / grand_total_ex01 for t in bm_totals_ex01] if grand_total_ex01 > 0 \
                       else [1.0 / len(benchmarks)] * len(benchmarks)
    means_ex01 = [
        sum(bm_weights_ex01[j] * ex01_pcts_all[j][i] for j in range(len(benchmarks)))
        for i in range(NUM_CATS)
    ]
    print("-" * len(hdr))
    print(f"{'Mean (Except01)':<28}" + "".join(f"{v:>7.2f}%" for v in means_ex01))
    print()

    # ---- Except012 table ------------------------------------------
    print(f"\n[broadcastsPerWakeUpCycleExcept012]")
    print(hdr)
    print("-" * len(hdr))
    ex012_pcts_all = []
    for bm in benchmarks:
        ex012_pct = to_percentages(cam_raw[bm], STAT_KEYS_EX012)
        ex012_pcts_all.append(ex012_pct)
        row = f"{bm:<28}" + "".join(f"{v:>7.2f}%" for v in ex012_pct)
        print(row)
    bm_totals_ex012   = [sum(cam_raw[bm].get(k, 0.0) for k in STAT_KEYS_EX012) for bm in benchmarks]
    grand_total_ex012 = sum(bm_totals_ex012)
    bm_weights_ex012  = [t / grand_total_ex012 for t in bm_totals_ex012] if grand_total_ex012 > 0 \
                        else [1.0 / len(benchmarks)] * len(benchmarks)
    means_ex012 = [
        sum(bm_weights_ex012[j] * ex012_pcts_all[j][i] for j in range(len(benchmarks)))
        for i in range(NUM_CATS)
    ]
    print("-" * len(hdr))
    print(f"{'Mean (Except012)':<28}" + "".join(f"{v:>7.2f}%" for v in means_ex012))
    print()

    generate_tikz(cam_raw, OUTPUT_TEX)


if __name__ == "__main__":
    main()
