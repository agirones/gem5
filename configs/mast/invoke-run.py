
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

parser.add_argument(
    "--cpu-width",
    type=int,
    required=False,
    help="Width for the backend of the processor: decode, rename, dispatch, issue, wb and commit."
)

parser.add_argument(
    "--output-dir",
    type=str,
    required=False,
    default="/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/runs/output",
    help="Base directory where simulation outputs and run-specific data will be stored."
)

parser.add_argument(
    "--config",
    type=str,
    required=False,
    default="_default_config",
    help="Path or name of the gem5 configuration script to use (e.g., 'configs/my_system.py' or 'custom_config')."
)

parser.add_argument(
    "--cpt",
    type=int,
    required=False,
    help="The checkpoint that would be executed."
)

args = parser.parse_args()


benchmark = ALL_BENCHMARKS[args.benchmark_num]

root = os.getcwd()

if args.config == "_default_config":
    args.config = f"{root}/configs/mast/profile-config-legacy.py"

def setup_run_dir():
    tgt = f"{args.output_dir}/width{args.cpu_width}/{benchmark.name}"
    if os.path.exists(tgt):
        shutil.rmtree(tgt)
    os.makedirs(tgt, exist_ok=True)
    os.chdir(tgt)

def cleanup():
    os.chdir(root)

def setup_cpt_dir(cpt):
    tgt = f"{args.output_dir}/width{args.cpu_width}/{benchmark.name}/{cpt}"
    if os.path.exists(tgt):
        shutil.rmtree(tgt)
    os.makedirs(tgt, exist_ok=True)
    os.chdir(tgt)


if args.mode == "cpt":
    print("Running in cpt mode.")
    simpoint_cpt_dir = "/cluster/projects/mast/checkpoints/simpoint-checkpoints"
    cpts = os.listdir(f"{simpoint_cpt_dir}/{benchmark.name}-cpt")
    cpts.sort()
    #assert(len(cpts) > 0)

    setup_run_dir()

    cpt = cpts[args.cpt]
    setup_cpt_dir(cpt)
    subprocess.run([f"{root}/build/X86/gem5.opt",
#                    "--debug-flags=O3PipeView",
#                    "--debug-flags=IEW",
#                    "--debug-flags=IQ",
#                    "--debug-flags=IQDEP",
#                    "--debug-flags=RegIndex",
#                    "--debug-flags=DebugSF",
#                    "--debug-flags=MemDepUnit",
#                    "--debug-flags=Commit",
#                    "--debug-flags=Rename",
#                    "--debug-flags=LSQUnit",
#                    "--debug-flags=DynInst",
#                    "--debug-flags=O3CPUAll",
#                    "--debug-file=trace.out",
#                    "--debug-start=18049387232646",
#                    "--debug-end=18049636479483",
#                    "--debug-break=18049636479483",
                    f"{args.config}",
                    "--benchmark-num", str(args.benchmark_num),
                    "--mode", "simrun",
                    "--simpoint-num", str(args.cpt),
                    "--cpu-width", str(args.cpu_width),
                    "--run-base-dir", args.output_dir])
    cleanup()
    exit(0)

if not args.mode == "simrun":
    setup_run_dir()
    subprocess.run([f"{root}/build/X86/gem5.opt",
                f"{args.config}",
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
#assert(len(cpts) > 0)

setup_run_dir()

for i in range(len(cpts)):
    cpt = cpts[i]
    setup_cpt_dir(cpt)
    subprocess.run([f"{root}/build/X86/gem5.opt",
#                    "--debug-flags=O3PipeView",
#                    "--debug-flags=IEW",
#                    "--debug-flags=IQ",
#                    "--debug-flags=IQDEP",
#                    "--debug-flags=RegIndex",
#                    "--debug-flags=DebugSF",
#                    "--debug-file=trace.out",
#                    "--debug-flags=CommitP",
#                    "--debug-start=1342141375473",
#                    "--debug-end=1464957618957",
                    f"{args.config}",
                    "--benchmark-num", str(args.benchmark_num),
                    "--mode", args.mode,
                    "--simpoint-num", str(i),
                    "--cpu-width", str(args.cpu_width),
                    "--run-base-dir", args.output_dir])
    cleanup()
