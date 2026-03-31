#!/usr/bin/env python3
"""
Collect per-benchmark weighted-average dispatch and broadcast statistics from
gem5 simpoint runs, for both the Baseline (12B_-1P) and Sereno (1B_2P)
configurations.

Output CSV columns:
  approach, benchmark, freq_ghz, numCycles,
  dispatchedNonReadySrcRegs, dispatchedReadySrcRegs,
  broadcastTotal, squashInducedBroadcasts,
  squashInducedBroadcastsWouldBroadcast, squashInducedBroadcastsWouldPrecise,
  broadcastExcludingSquash

broadcastTotal                      = broadcastWakeUp + squashInducedBroadcasts
broadcastExcludingSquash            = broadcastWakeUp
squashInducedBroadcastsWouldBroadcast = squash-induced regs that would have broadcast anyway
squashInducedBroadcastsWouldPrecise   = squash-induced regs that would have had a precise wakeup
"""

import os
import re
import csv
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[4]     # .../gem5-NTNU/
RUNS_ROOT = REPO_ROOT / "runs" / "output" / "micro26"

APPROACHES = {
    "Baseline": RUNS_ROOT / "baseline" / "12B_-1P" / "width8",
    "Sereno":   RUNS_ROOT / "whisper"  / "1B_2P"   / "width8",
}

OUTPUT_CSV = RUNS_ROOT / "csv" / "dispatch_broadcast_stats.csv"

# ---------------------------------------------------------------------------
# Stats to collect (exact names as they appear in stats.txt)
# ---------------------------------------------------------------------------
STAT_KEYS = [
    "simFreq",
    "system.clk_domain.clock",
    "system.cpu.numCycles",
    "system.cpu.iew.broadcastWakeUp",
    "system.cpu.iew.squashInducedBroadcasts",
    "system.cpu.iew.squashInducedBroadcastsWouldBroadcast",
    "system.cpu.iew.squashInducedBroadcastsWouldPrecise",
    "system.cpu.iew.dispatchedNonReadyIntFpVecSrcOps",
    "system.cpu.iew.dispatchedReadyIntFpVecSrcOps",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_STAT_RE = re.compile(r'^(\S+)\s+([\d.e+\-]+)')
_BEGIN_RE = re.compile(r'-{10,} Begin Statistics -{10,}')


def parse_last_section(stats_path: Path) -> dict:
    """Parse the LAST Begin/End section of a stats.txt (= the ROI, not warmup)."""
    text = stats_path.read_text()
    sections = _BEGIN_RE.split(text)
    # sections[0] is preamble; sections[1..] are stat blocks
    last = sections[-1] if len(sections) > 1 else sections[0]
    result = {}
    for line in last.splitlines():
        m = _STAT_RE.match(line)
        if m:
            result[m.group(1)] = float(m.group(2))
    return result


def weight_from_dir(dirname: str) -> float:
    """Extract the simpoint weight embedded in a checkpoint directory name."""
    m = re.search(r'_weight_([\d.]+)_', dirname)
    return float(m.group(1)) if m else 1.0


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------
rows = []

for approach, width8_dir in APPROACHES.items():
    if not width8_dir.exists():
        print(f"WARNING: {width8_dir} not found – skipping {approach}")
        continue

    for bench_dir in sorted(width8_dir.iterdir()):
        if not bench_dir.is_dir():
            continue
        benchmark = bench_dir.name

        wsum = {k: 0.0 for k in STAT_KEYS}
        weight_total = 0.0

        for sp_dir in sorted(bench_dir.iterdir()):
            stats_file = sp_dir / "m5out" / "stats.txt"
            if not stats_file.exists():
                continue

            w = weight_from_dir(sp_dir.name)
            stats = parse_last_section(stats_file)
            for key in STAT_KEYS:
                wsum[key] += stats.get(key, 0.0) * w
            weight_total += w

        if weight_total == 0.0:
            print(f"WARNING: no simpoints found for {approach}/{benchmark} – skipping")
            continue

        # Weighted average (weights typically sum to ~1.0 per benchmark)
        wavg = {k: wsum[k] / weight_total for k in STAT_KEYS}

        sim_freq  = wavg["simFreq"]               # ticks/second
        clock     = wavg["system.clk_domain.clock"]  # ticks/cycle
        freq_ghz  = sim_freq / clock / 1e9

        num_cycles    = wavg["system.cpu.numCycles"]
        non_ready     = wavg["system.cpu.iew.dispatchedNonReadyIntFpVecSrcOps"]
        ready         = wavg["system.cpu.iew.dispatchedReadyIntFpVecSrcOps"]
        broadcast_wu          = wavg["system.cpu.iew.broadcastWakeUp"]
        squash_ind            = wavg["system.cpu.iew.squashInducedBroadcasts"]
        squash_would_bcast    = wavg["system.cpu.iew.squashInducedBroadcastsWouldBroadcast"]
        squash_would_precise  = wavg["system.cpu.iew.squashInducedBroadcastsWouldPrecise"]

        broadcast_total       = broadcast_wu + squash_ind
        broadcast_excl_squash = broadcast_wu   # broadcast_total - squash_ind

        rows.append({
            "approach":                             approach,
            "benchmark":                            benchmark,
            "freq_ghz":                             round(freq_ghz, 6),
            "numCycles":                            round(num_cycles, 2),
            "dispatchedNonReadySrcRegs":            round(non_ready, 2),
            "dispatchedReadySrcRegs":               round(ready, 2),
            "broadcastTotal":                       round(broadcast_total, 2),
            "squashInducedBroadcasts":              round(squash_ind, 2),
            "squashInducedBroadcastsWouldBroadcast": round(squash_would_bcast, 2),
            "squashInducedBroadcastsWouldPrecise":  round(squash_would_precise, 2),
            "broadcastExcludingSquash":             round(broadcast_excl_squash, 2),
        })

        print(f"  {approach:10s}  {benchmark:30s}  "
              f"freq={freq_ghz:.3f} GHz  cycles={num_cycles:.0f}  "
              f"broadcasts={broadcast_total:.0f}  squash={squash_ind:.0f}  "
              f"(wouldBcast={squash_would_bcast:.0f}, wouldPrecise={squash_would_precise:.0f})")

# ---------------------------------------------------------------------------
# Write CSV
# ---------------------------------------------------------------------------
OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
fieldnames = [
    "approach", "benchmark", "freq_ghz", "numCycles",
    "dispatchedNonReadySrcRegs", "dispatchedReadySrcRegs",
    "broadcastTotal", "squashInducedBroadcasts",
    "squashInducedBroadcastsWouldBroadcast", "squashInducedBroadcastsWouldPrecise",
    "broadcastExcludingSquash",
]
with OUTPUT_CSV.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")
