#!/bin/bash
# Run all pyperformance ffrun jobs for Sereno (broadcastMax=1,
# dependentsThreshold=2) from the sereno worktree.
#
# See ../run_experiment.sh for the full workflow and output layout.
#
# Usage:
#   ./run_experiment.sh [MAIN_GEM5_ROOT]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_ROOT="${1:-/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU}"

exec "${SCRIPT_DIR}/../run_experiment.sh" sereno "${MAIN_ROOT}"
