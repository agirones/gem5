import os
import shutil

dirs = os.listdir(".")

print(dirs)
for name in dirs:
    if not name.startswith("6"):
        continue
    cpt_name = [entry for entry in os.listdir(f"{name}/m5out") if entry.endswith("cpt")]
    assert(len(cpt_name) == 1)
    cpt_name = cpt_name[0]
    src = f"{name}/m5out/{cpt_name}"
    tgt = f"legacy-checkpoints/{name}-cpt"
    shutil.copytree(src, tgt)

