
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

setup_run_dir()

subprocess.run([f"{root}/build/X86/gem5.opt",
                f"{root}/configs/mast/profile-config-legacy.py",
                "--benchmark-num", str(args.benchmark_num)])

cleanup()