import os
import shutil

dirs = os.listdir("legacy-checkpoints")

root_dir = "/cluster/projects/mast/checkpoints/simpoint-checkpoints"

for name in dirs:
    if not name.startswith("6"):
        continue
    tgt_dir = f"{root_dir}/{name}"
    if not os.path.exists(tgt_dir):
        os.mkdir(tgt_dir)
    cpt_names = [entry for entry in os.listdir(f"legacy-checkpoints/{name}") if entry.startswith("cpt")]
    if (len(cpt_names) < 1):
        print(f"Error: benchmark {name} does not have any simpoint_checkpoints, continuing...")
        continue
    assert(len(cpt_names) >= 1)
    for cpt in cpt_names:
        src = f"legacy-checkpoints/{name}/{cpt}"
        tgt = f"{tgt_dir}/{cpt}"
        if os.path.exists(tgt):
            continue
        shutil.copytree(src, tgt)

