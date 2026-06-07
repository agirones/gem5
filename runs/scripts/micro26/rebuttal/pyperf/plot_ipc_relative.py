#!/usr/bin/env python3
"""
Generates a standalone PGF/TikZ (pgfplots) bar chart showing the IPC change
(in %) of Sereno relative to the baseline for pyperformance benchmarks.

Per-benchmark value: ((sereno_IPC / baseline_IPC) - 1) * 100

The rightmost group shows the Equal-Work Speedup (EWS) as defined by
Eeckhout (2024): EWS = ((HM_sereno / HM_baseline) - 1) * 100
where HM_* is the harmonic mean of raw IPCs over all benchmarks.
Harmonic means are used exclusively — no arithmetic or geometric means.

Data sources:
  Baseline : runs/output/micro26/rebuttal/pyperf/baseline
  Sereno   : runs/output/micro26/rebuttal/pyperf/sereno

IPC per benchmark uses the same formula as plot_ipc_relative.py:
    IPC = simInsts / numCycles
from the final stats dump.  ffrun restores an Atomic CPU and switches to O3
for the measured region, so numCycles is read from system.switch_cpus when
system.cpu.numCycles is zero.

Output: runs/output/micro26/rebuttal/pyperf/ipc_relative.tex
"""

import math
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[5]  # .../gem5-NTNU/

PYPERF_DIR = ROOT / "runs/output/micro26/rebuttal/pyperf"
BASELINE_DIR = PYPERF_DIR / "baseline"
SERENO_DIR = PYPERF_DIR / "sereno"

OUTPUT_TEX = PYPERF_DIR / "ipc_relative.tex"

INSTS_STAT = "simInsts"
CPU_CYCLES_STAT = "system.cpu.numCycles"
SWITCH_CYCLES_STAT = "system.switch_cpus.numCycles"

# Experiment submission order (only benchmarks present in both dirs are plotted).
BENCHMARK_ORDER = ["float", "nbody", "chaos", "go", "richards"]

BAR_COLOR = ("clrSereno", 31, 119, 180)

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def extract_benchmark(stats_file: Path) -> str:
    """
    Return the benchmark name from a pyperf ffrun stats.txt path.

    Expected layout:
        {base_dir}/width8/{benchmark}/m5out/stats.txt
    """
    return stats_file.parent.parent.name


def parse_stats(stats_file: Path) -> Optional[tuple[float, float]]:
    """
    Return (simInsts, numCycles) from the final stats dump.

    Matches plot_ipc_relative.py (simInsts / numCycles).  For ffrun runs the
    measured O3 region is on switch_cpus, so fall back to that stat when the
    primary CPU reports zero cycles in the final dump.
    """
    in_dump = False
    last: Optional[tuple[float, float]] = None
    current_insts: Optional[float] = None
    current_cpu_cycles: Optional[float] = None
    current_switch_cycles: Optional[float] = None

    try:
        with open(stats_file, "r", errors="replace") as f:
            for line in f:
                if "---------- Begin Simulation Statistics ----------" in line:
                    in_dump = True
                    current_insts = current_cpu_cycles = current_switch_cycles = None
                    continue
                if "---------- End Simulation Statistics   ----------" in line:
                    cycles = current_cpu_cycles
                    if cycles is None or cycles == 0:
                        cycles = current_switch_cycles
                    if current_insts is not None and cycles is not None and cycles > 0:
                        last = (current_insts, cycles)
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
                elif parts[0] == CPU_CYCLES_STAT:
                    try:
                        current_cpu_cycles = float(parts[1])
                    except ValueError:
                        pass
                elif parts[0] == SWITCH_CYCLES_STAT:
                    try:
                        current_switch_cycles = float(parts[1])
                    except ValueError:
                        pass
    except OSError:
        return None

    return last


def collect_ipc(base_dir: Path) -> dict[str, float]:
    """
    Return {benchmark: IPC} from ffrun measurement stats only.

    Each benchmark has a single run (no simpoint weights): IPC = insts / cycles.
    """
    stats_files = sorted(base_dir.glob("width8/*/m5out/stats.txt"))
    if not stats_files:
        print(f"  WARNING: no measurement stats.txt found under {base_dir}")
        return {}

    ipc_by_benchmark: dict[str, float] = {}

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
        ipc_by_benchmark[benchmark] = insts / cycles

    return ipc_by_benchmark


def harmonic_mean(values: list[float]) -> float:
    if not values:
        return float("nan")
    return len(values) / sum(1.0 / v for v in values if v > 0)


def clean_label(benchmark: str) -> str:
    return benchmark.replace("_", r"\_")


def _escape_latex(s: str) -> str:
    return s.replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")


# ---------------------------------------------------------------------------
# LaTeX / pgfplots generation
# ---------------------------------------------------------------------------


def _nice_axis_limits(values: list[float]) -> tuple[float, float, list[int]]:
    """Pick ymin/ymax and ytick values with a little padding."""
    finite = [v for v in values if v == v]
    if not finite:
        return -5.0, 5.0, [-5, 0, 5]

    vmin = min(finite)
    vmax = max(finite)
    span = max(vmax - vmin, 0.5)
    pad = max(0.15 * span, 0.1)
    ymin = math.floor((vmin - pad) * 2) / 2
    ymax = math.ceil((vmax + pad) * 2) / 2

    step = 0.5 if (ymax - ymin) <= 3 else 1.0
    ticks: list[int] = []
    tick = ymin
    while tick <= ymax + 1e-9:
        ticks.append(int(tick) if tick == int(tick) else tick)
        tick += step
    return ymin, ymax, ticks


def generate_tikz(
    baseline_ipc: dict[str, float],
    sereno_ipc: dict[str, float],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    common = set(baseline_ipc) & set(sereno_ipc)
    all_benchmarks = [bm for bm in BENCHMARK_ORDER if bm in common]
    all_benchmarks += sorted(common - set(all_benchmarks))

    if not all_benchmarks:
        print("No common benchmarks between baseline and Sereno.")
        return

    x_labels = all_benchmarks + ["HarmonicMean"]

    pct: dict[str, float] = {}
    sereno_vals: list[float] = []
    baseline_vals: list[float] = []
    for bm in all_benchmarks:
        base = baseline_ipc[bm]
        val = sereno_ipc[bm]
        if base > 0:
            pct[bm] = (val / base - 1.0) * 100.0
            sereno_vals.append(val)
            baseline_vals.append(base)

    hm_sereno = harmonic_mean(sereno_vals)
    hm_baseline = harmonic_mean(baseline_vals)
    ews_pct = (
        (hm_sereno / hm_baseline - 1.0) * 100.0 if hm_baseline > 0 else float("nan")
    )

    vals_bm = [pct[bm] for bm in all_benchmarks]
    vals = vals_bm + [ews_pct]
    coord_strs = [
        f"({label}, {v:.6f})"
        for label, v in zip(x_labels, vals)
        if v == v
    ]
    coord_body = "\n        ".join(coord_strs)

    sym_coords = ", ".join(x_labels)
    display_labels = [clean_label(lb) for lb in all_benchmarks] + [r"\textbf{HMean}"]
    xticklabels = ", ".join(display_labels)

    ymin, ymax, yticks = _nice_axis_limits(vals)
    ytick_str = ", ".join(str(t) for t in yticks)

    cname, r, g, b = BAR_COLOR
    define_colors = f"\\definecolor{{{cname}}}{{RGB}}{{{r},{g},{b}}}\n"

    tex = (
        r"\documentclass[tikz]{standalone}" "\n"
        r"\usepackage{pgfplots}" "\n"
        r"\pgfplotsset{compat=1.18}" "\n"
        "\n"
        r"\pgfdeclarelayer{background}" "\n"
        r"\pgfsetlayers{background,main}" "\n"
        "\n"
        + define_colors +
        "\n"
        r"\begin{document}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"\begin{axis}[" "\n"
        r"    width           = 0.55\textwidth, height=4cm, scale only axis," "\n"
        r"    ybar," "\n"
        r"    bar width       = 8pt," "\n"
        r"    enlarge x limits= 0.08," "\n"
        f"    symbolic x coords = {{{sym_coords}}},\n"
        r"    xtick           = data," "\n"
        f"    xticklabels     = {{{xticklabels}}},\n"
        r"    x tick label style = {rotate=90, anchor=east}," "\n"
        f"    ymin            = {ymin:.1f},\n"
        f"    ymax            = {ymax:.1f},\n"
        f"    ytick           = {{{ytick_str}}},\n"
        r"    ylabel          = {Normalized performance}," "\n"
        r"    ymajorgrids     = true," "\n"
        r"    grid style      = {dashed, gray!30}," "\n"
        r"    axis line style = {gray!60}," "\n"
        r"    tick style      = {gray!60}," "\n"
        r"    tick label style= {font=\scriptsize}," "\n"
        r"    yticklabel        = {\pgfmathprintnumber\tick\%}," "\n"
        r"    after end axis/.code={" "\n"
        r"        \begin{pgfonlayer}{background}" "\n"
        r"            \fill[gray!60] ([xshift=-11pt]{axis cs:HarmonicMean,\pgfkeysvalueof{/pgfplots/ymin}}) rectangle (rel axis cs:1,1);" "\n"
        r"        \end{pgfonlayer}" "\n"
        r"    }," "\n"
        r"]" "\n"
        "\n"
        f"    \\addplot[\n"
        f"        fill={cname},\n"
        f"        draw={cname}!60!black,\n"
        f"        line width=0.4pt,\n"
        f"    ] coordinates {{\n"
        f"        {coord_body}\n"
        f"    }};\n"
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
    for label, base_dir in (("Baseline", BASELINE_DIR), ("Sereno", SERENO_DIR)):
        if not base_dir.exists():
            print(f"ERROR: directory not found: {base_dir}")
            return

    print("Collecting IPC for Baseline …")
    baseline_ipc = collect_ipc(BASELINE_DIR)
    print(f"  → {len(baseline_ipc)} benchmarks found")

    print("Collecting IPC for Sereno …")
    sereno_ipc = collect_ipc(SERENO_DIR)
    print(f"  → {len(sereno_ipc)} benchmarks found")

    common = sorted(set(baseline_ipc) & set(sereno_ipc))
    if not common:
        print("No common benchmarks – nothing to plot.")
        return

    ordered = [bm for bm in BENCHMARK_ORDER if bm in common]
    ordered += sorted(set(common) - set(ordered))

    print("\nBenchmark                     Baseline IPC   Sereno IPC   Change (%)")
    print("-" * 72)
    sereno_vals: list[float] = []
    baseline_vals: list[float] = []
    for bm in ordered:
        base = baseline_ipc[bm]
        val = sereno_ipc[bm]
        pct = (val / base - 1.0) * 100.0 if base > 0 else float("nan")
        print(f"{bm:<28} {base:>12.6f} {val:>12.6f} {pct:>11.2f}%")
        sereno_vals.append(val)
        baseline_vals.append(base)

    hm_baseline = harmonic_mean(baseline_vals)
    hm_sereno = harmonic_mean(sereno_vals)
    ews_pct = (hm_sereno / hm_baseline - 1.0) * 100.0 if hm_baseline > 0 else float("nan")
    print("-" * 72)
    print(f"{'Harmonic Mean':<28} {hm_baseline:>12.6f} {hm_sereno:>12.6f} {ews_pct:>11.2f}%")

    generate_tikz(baseline_ipc, sereno_ipc, OUTPUT_TEX)


if __name__ == "__main__":
    main()
