import os
import shutil

dirs = os.listdir(".")

print(dirs)
for name in dirs:
    if not name.startswith("6"):
        continue
    bb_name = [entry for entry in os.listdir(f"{name}/m5out") if entry.endswith("bb.gz")]
    assert(len(bb_name) == 1)
    bb_name = bb_name[0]
    src = f"{name}/m5out/{bb_name}"
    tgt = f"/cluster/projects/mast/simpoints/bbv-analysis/{name}.bb.gz"
    shutil.copy(src, tgt)

