
import argparse
import os
import shutil
import subprocess
import sys


from benchmarks import ALL_BENCHMARKS

#We have to do it like this cause invoking ./build/X86/gem5.opt config
#automatically makes the m5 folder before we are ready

def int_or_default(value, default_val):
    if value == "" or value is None:
        return default_val
    return int(value)

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
    default=8,
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

parser.add_argument(
    "--broadcastMax",
    type=int,
    required=False,
    default=12,
    help="The maximum number of broadcast in the IQ in one cycle."
)

parser.add_argument(
    "--dependentsThreshold",
    type=int,
    required=False,
    default=-1,
    help="The threshold of dependents so if it's higher, the instuction broadcasts when during wake up."
)

parser.add_argument(
    "--iq-size",
    type=lambda x: int_or_default(x, 256),
    required=False,
    default=256,
    help="Sets the size of the IQ."
)

parser.add_argument(
    "--lq-size",
    type=lambda x: int_or_default(x, 256),
    required=False,
    default=256,
    help="Sets the size of the LQ."
)

parser.add_argument(
    "--sq-size",
    type=lambda x: int_or_default(x, 256),
    required=False,
    default=256,
    help="Sets the size of the SQ."
)

parser.add_argument(
    "--l1-latency",
    type=lambda x: int_or_default(x, 1),
    required=False,
    default=1,
    help="Sets the tag and data latency for the L1I and L1D caches."
)

parser.add_argument(
    "--simpoint-num",
    type=int,
    required=False,
    default=None,
    help="If specified, run only this single simpoint index. "
         "Otherwise run all simpoints sequentially (legacy behaviour)."
)

parser.add_argument(
    "--gdb",
    action="store_true",
    help="Run the simulation inside GDB for debugging"
)

args = parser.parse_args()


benchmark = ALL_BENCHMARKS[args.benchmark_num]

root = os.getenv('GEM5_ROOT', os.getcwd())

cpt_default = "/cluster/projects/mast/checkpoints/simpoint-checkpoints"
cpt_base = os.getenv("GEM5_CPTS", cpt_default)
simpoint_cpt_dir = f"{cpt_base}/{benchmark.name}-cpt"

if args.config == "_default_config":
    args.config = f"{root}/configs/mast/profile-config-legacy.py"

args.output_dir = os.path.abspath(args.output_dir)

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
simpoint_cpt_dir = os.getenv("GEM5_CPTS", "/cluster/projects/mast/checkpoints/simpoint-checkpoints")
cpts = os.listdir(f"{simpoint_cpt_dir}/{benchmark.name}-cpt")
cpts.sort()
#assert(len(cpts) > 0)

if args.simpoint_num is not None:
    # Single-simpoint mode: safe for parallel SLURM jobs.
    # Do NOT rm -rf the whole benchmark dir; just ensure parent exists.
    parent = f"{args.output_dir}/width{args.cpu_width}/{benchmark.name}"
    os.makedirs(parent, exist_ok=True)
    indices = [args.simpoint_num]
else:
    # Legacy: run all simpoints sequentially, clearing the benchmark dir first.
    setup_run_dir()
    indices = range(len(cpts))

container_path = "/cluster/home/andreug/research/EECS-NTNU/gem5-NTNU/mast_gem5.sif"

for i in indices:
    cpt = cpts[i]
    setup_cpt_dir(cpt)

    binary_type = "gem5.debug" if args.gdb else "gem5.opt"
    executable = f"{root}/build/X86/{binary_type}"

    cmd = ["apptainer", "exec", "-B", "/cluster:/cluster", container_path]

    if args.gdb:
        cmd.extend(["gdb", "--args"])

    cmd.append(executable)
    cmd.extend([
        f"{args.config}",
        "--benchmark-num", str(args.benchmark_num),
        "--mode", args.mode,
        "--simpoint-num", str(i),
        "--cpu-width", str(args.cpu_width),
        "--run-base-dir", args.output_dir,
        "--iq-size", str(args.iq_size),
        "--lq-size", str(args.lq_size),
        "--sq-size", str(args.sq_size),
        "--broadcastMax", str(args.broadcastMax),
        "--dependentsThreshold", str(args.dependentsThreshold),
        "--l1-latency", str(args.l1_latency),
    ])

    result = subprocess.run(cmd)
    stats_path = os.path.join(os.getcwd(), "stats.txt")

    if result.returncode != 0:
        if os.path.exists(stats_path):
            print(f"Warning: gem5 Segfaulted during teardown (Exit Code {result.returncode}).")
            print(f"Success: {stats_path} exists. Proceeding to next task.")
        else:
            print(f"Critical Error: gem5 crashed and NO stats found at {stats_path}.")
            sys.exit(1)

    cleanup()
