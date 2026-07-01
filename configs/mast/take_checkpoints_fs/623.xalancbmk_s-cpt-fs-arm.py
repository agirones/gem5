"""
AUTO-GENERATED ARM full-system KVM SimPoint checkpoint config for 623.xalancbmk_s.

Delegates to configs/mast/fs_take_checkpoints.py. Regenerate with:
  python3 scripts/generate_fs_cpt_configs.py --force
"""

import sys
from pathlib import Path

# gem5 puts take_checkpoints_fs/ on sys.path, not mast/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fs_take_checkpoints import run

run("623.xalancbmk_s", sys.argv[1:])
