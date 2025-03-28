
import argparse
import os
import shutil
import subprocess


from benchmarks import ALL_BENCHMARKS

#We have to do it like this cause invoking ./build/X86/gem5.opt config
#automatically makes the m5 folder before we are ready
parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)

parser.add_argument(
    "--benchmark-num",
    type=int,
    required=True,
    help="which benchmark from spec17 speed suite to run"
)

parser.add_argument(
    "--mode",
    type=str,
    action="store",
    required=True,
    help="which mode to run, valid options are cpt, profile, simtake, simrun"
)

args = parser.parse_args()


benchmark = ALL_BENCHMARKS[args.benchmark_num]

root = os.getcwd()

def setup_run_dir():
    tgt = f"{root}/runs/{benchmark.name}"
    if os.path.exists(tgt):
        shutil.rmtree(tgt)
    os.mkdir(tgt)
    os.chdir(tgt)

def cleanup():
    os.chdir(root)

def setup_cpt_dir(cpt):
    tgt = f"{root}/runs/{benchmark.name}/{cpt}"
    if os.path.exists(tgt):
        shutil.rmtree(tgt)
    os.mkdir(tgt)
    os.chdir(tgt)

if not args.mode == "simrun":
    setup_run_dir()
    subprocess.run([f"{root}/build/X86/gem5.opt",
                f"{root}/configs/mast/profile-config-legacy.py",
                "--benchmark-num", str(args.benchmark_num),
                "--mode", args.mode])
    cleanup()
    exit(0)

# gem5 can't reinstantiate with new checkpoints
# so when we want to do a simpoint run, we have to manage 
# each of the checkpoints individually, which takes some effort
simpoint_cpt_dir = "/cluster/projects/mast/checkpoints/simpoint-checkpoints"
cpts = os.listdir(f"{simpoint_cpt_dir}/{benchmark.name}-cpt")
cpts.sort()
assert(len(cpts) > 0)

setup_run_dir()

for i in range(len(cpts)):
    cpt = cpts[i]
    setup_cpt_dir(cpt)
    subprocess.run([f"{root}/build/X86/gem5.opt",
                    f"{root}/configs/mast/profile-config-legacy.py",
                    "--benchmark-num", str(args.benchmark_num),
                    "--mode", args.mode,
                    "--simpoint-num", str(i)])
    cleanup()
