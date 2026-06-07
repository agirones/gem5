import argparse
from os.path import join as joinpath
import m5
from gem5.isas import ISA 

from m5.objects import *
from m5.util import (
    addToPath,
    fatal,
    warn,
)

from gem5.isas import ISA 

current_dir = os.path.dirname(os.path.abspath(__file__))
configs_dir = os.path.abspath(os.path.join(current_dir, ".."))
addToPath(current_dir)
addToPath(configs_dir)

from common import (
    MemConfig,
    ObjectList,
    Options,
    Simulation
)

from common.Caches import *
from common.FSConfig import *
from common.SysPaths import *

from m5.objects.Prefetcher import (
    PIFPrefetcher,
#    STeMSPrefetcher,
#    BOPPrefetcher,
    DCPTPrefetcher,
    StridePrefetcher
)

from benchmarks import ALL_BENCHMARKS


parser = argparse.ArgumentParser()
Options.addCommonOptions(parser)
Options.addFSOptions(parser)

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
    "--simpoint-num",
    type=int,
    required=False,
    help="Which simpoint to run. Required if simrun mode",
)

parser.add_argument(
    "--cpu-width",
    type=int,
    required=False,
    help="Width for the backend of the processor: decode, rename, dispatch, issue, wb and commit."
)

parser.add_argument(
    "--core-scale",
    type=float,
    required=False,
    default=1.0,
    help="Scale factor applied to the detailed core's superscalar widths and "
         "structure sizes (fetch/decode/.../commit widths, IQ/LQ/SQ, ROB and "
         "physical register files). 1.0 = baseline, 1.5 = x1.5, 2.0 = double, "
         "4.0 = quadruple."
)

parser.add_argument(
    "--run-base-dir", type=str,
    default="_default_run_dir_runs",
    help="Base directory for simulation runs (e.g., 'my_sims' or 'data/runs')"
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
    type=int,
    required=False,
    default=256,
    help="Sets the size of the IQ."
)

parser.add_argument(
    "--lq-size",
    type=int,
    required=False,
    default=256,
    help="Sets the size of the LQ."
)

parser.add_argument(
    "--sq-size",
    type=int,
    required=False,
    default=256,
    help="Sets the size of the SQ."
)

parser.add_argument(
    "--l1-latency",
    type=int,
    required=False,
    default=1,
    help="Sets the tag and data latency for the L1I and L1D caches."
)

parser.add_argument(
    "--warmup-length",
    type=int,
    required=False,
    default=-1,
    help="Detailed (O3) warmup length in instructions before the measured "
         "region. If <0 (default) the warmup is read from the checkpoint "
         "directory name (legacy behaviour)."
)

parser.add_argument(
    "--fast-forward-length",
    type=int,
    required=False,
    default=0,
    help="Number of instructions to fast-forward in an atomic CPU before the "
         "detailed warmup begins. 0 (default) keeps the legacy behaviour: "
         "restore straight into the O3 CPU with no fast-forward and no CPU "
         "switch. When >0 the run restores into an atomic CPU, fast-forwards "
         "this many instructions, then switches to the O3 CPU for warmup + "
         "measurement (caches are flushed at the switch so warmup starts cold)."
)

parser.add_argument(
    "--measure-length",
    type=int,
    required=False,
    default=100000000,
    help="Detailed (O3) measured-region length in instructions. Only used by "
         "the 'ffrun' mode (fast-forward from the post-boot checkpoint). For "
         "'simrun' the measured region is fixed by the SimPoint interval baked "
         "into the checkpoint name and this option is ignored."
)

args = parser.parse_args()

benchmark = ALL_BENCHMARKS[args.benchmark_num]

script_dir = os.path.dirname(__file__)
root = os.path.abspath(f"{script_dir}/../..")

if args.run_base_dir == "_default_run_dir_runs":
    args.run_base_dir = f"{root}/runs/output"

checkpoints = os.getenv("GEM5_POSTBOOT_CPTS", f"{root}/runs/legacy-checkpoints")
simpoints_dir = f"/cluster/projects/mast/simpoints/simpoints"
simpoint_cpt_dir = os.getenv("GEM5_CPTS", "/cluster/projects/mast/checkpoints/simpoint-checkpoints")

disk_image = os.getenv("GEM5_DISK", "/cluster/projects/mast/full-system/disk-images/x86-ubuntu-with-spec17")
root_device = "/dev/sda2"
mem_size = "16GiB"
os_type = "linux"

kernel_cmd = " ".join([
    "earlyprintk=ttyS0",
    "console=ttyS0",
    "lpj=7999923",
    "root=/dev/sda2",
    "no_systemd=true"
])

kernel = os.getenv("GEM5_KERNEL", "/cluster/projects/mast/full-system/kernels/x86-linux-kernel-5.4.0-105-generic")


def configure_detailed_cpu(cpu):
#    for fupool in cpu.fuPool.FUList:
#        fupool.count = 8

    fu_list = cpu.fuPool.FUList[0].count = 8 # IntAlu
    fu_list = cpu.fuPool.FUList[1].count = 2 # IntMultDiv
    fu_list = cpu.fuPool.FUList[3].count = 3 # ReadPort
    fu_list = cpu.fuPool.FUList[4].count = 2 # SIMD_Unit
    fu_list = cpu.fuPool.FUList[6].count = 2 # PredALU
    fu_list = cpu.fuPool.FUList[7].count = 0 # WritePort

    # Scale the core's widths and structure sizes by --core-scale so the same
    # config can model a bigger core (1.5x / 2x / 4x ...). Results are rounded
    # to the nearest integer and clamped to >= 1.
    def scaled(base):
        return max(1, int(round(base * args.core_scale)))

    cpu.fetchWidth = scaled(10)
    cpu.decodeWidth = scaled(10)
    cpu.renameWidth = scaled(10)
    cpu.dispatchWidth = scaled(10)
    cpu.issueWidth = scaled(12)
    cpu.wbWidth = scaled(12)
    cpu.commitWidth = scaled(12)

    cpu.numIQEntries = scaled(args.iq_size)
    cpu.numPhysFloatRegs = scaled(630)
    cpu.numPhysIntRegs = scaled(630)
    cpu.numROBEntries = scaled(630)
    cpu.LQEntries = scaled(args.lq_size)
    cpu.SQEntries = scaled(args.sq_size)

    cpu.backComSize = 30
    cpu.forwardComSize = 512

    cpu.branchPred.btb.numEntries = 8192
    cpu.branchPred.btb.associativity = 4

    cpu.broadcastMax = args.broadcastMax
    cpu.dependentsThreshold = args.dependentsThreshold


def config_system(system):
    for cpu in system.cpu:
        configure_detailed_cpu(cpu)


#test_sys.init_param = args.init_param
def config_cache(system):

    dcache_class, icache_class, l2_cache_class, l3_cache_class, walk_cache_class = (
        L1_DCache,
        L1_ICache,
        L2Cache,
        L3Cache,
        None
    )

    system.cache_line_size = cacheline_size

    l3_config = dict(
        clk_domain=system.cpu_clk_domain,
        tag_latency="30",
        data_latency="30",
        size="32MiB",
        assoc="16",
#        tag_latency="35",
#        data_latency="35",
#        size="3MiB",
#        assoc="12",
    )

    l2_config = dict(
        clk_domain=system.cpu_clk_domain,
        size="1280KiB",
        assoc="10",
        tag_latency="4",
        data_latency="4",
#        tag_latency="11",
#        data_latency="11",
#        size="1MiB",
#        assoc="16",
    )

    l1i_config = dict(
        size="32KiB",
        assoc="8",
        tag_latency=str(args.l1_latency),
        data_latency=str(args.l1_latency),
#        tag_latency="4",
#        data_latency="4",
    )

    l1d_config = dict(
        size="48KiB",
        assoc="12",
        tag_latency=str(args.l1_latency),
        data_latency=str(args.l1_latency),
#        tag_latency="5",
#        data_latency="5",
#        size="32KiB",
#        assoc="8",
#        tag_latency="4",
#        data_latency="4",
    )

    system.l3 = l3_cache_class(**l3_config)
    system.l3.prefetcher = DCPTPrefetcher()
#    system.l3.prefetcher = STeMSPrefetcher(active_generation_table_entries = "256",
#                                           active_generation_table_assoc = 256,
#                                           pattern_sequence_table_entries = "65536",
#                                           pattern_sequence_table_assoc = 65536,
#                                           region_miss_order_buffer_entries = 524288,
#                                           reconstruction_entries = 1024)

    system.l2 = l2_cache_class(**l2_config)
    system.l2.prefetcher = DCPTPrefetcher()
#    system.l2.prefetcher = BOPPrefetcher(bad_score = 1,
#                                         offset_list_size = 52,
#                                         rr_size = 256
#                                         )

    system.tol3bus = L3XBar(clk_domain=system.cpu_clk_domain)
    system.l3.cpu_side = system.tol3bus.mem_side_ports
    system.l3.mem_side = system.membus.cpu_side_ports

    system.tol2bus = L2XBar(clk_domain=system.cpu_clk_domain)
    system.l2.cpu_side = system.tol2bus.mem_side_ports
    system.l2.mem_side = system.tol3bus.cpu_side_ports

    icache = icache_class(**l1i_config)
    icache.prefetcher = PIFPrefetcher()

    dcache = dcache_class(**l1d_config)
    dcache.prefetcher = StridePrefetcher()
#    dcache.prefetcher = BOPPrefetcher()

    iwalkcache = PageTableWalkerCache()
    dwalkcache = PageTableWalkerCache()
    system.cpu[0].addPrivateSplitL1Caches(
        icache, dcache, iwalkcache, dwalkcache
    )

    system.cpu[0].createInterruptController()
    system.cpu[0].connectAllPorts(
        system.tol2bus.cpu_side_ports,
        system.membus.cpu_side_ports,
        system.membus.mem_side_ports
    )

    return system

def parseSimpoints(benchmark, interval_length, warmup_length, testsys):
    simpoints = []
    simpoint_start_insts = []
    with open(f"{simpoints_dir}/{benchmark.name}.simpoints", "r") as simpoints_file,\
         open(f"{simpoints_dir}/{benchmark.name}.weights", "r") as weights_file:
        sim_lines = simpoints_file.readlines()
        weight_lines = weights_file.readlines()
        assert len(sim_lines) == len(weight_lines), f"different sim ({len(sim_lines)} and weight ({len(weight_lines)}))"

        for i in range(len(sim_lines)):
            interval = int(sim_lines[i].split()[0])
            weight = float(weight_lines[i].split()[0])
            if (interval * interval_length - warmup_length > 0):
                starting_inst_count = interval * interval_length - warmup_length
                actual_warmup_length = warmup_length
            else: 
                starting_inst_count = 0
                actual_warmup_length = interval * interval_length

            simpoints.append(
                (interval, weight, starting_inst_count, actual_warmup_length)
            )
            simpoint_start_insts.append(starting_inst_count)
    testsys.cpu[0].simpoint_start_insts = simpoint_start_insts
    return simpoints


def get_sim_work_dir():
    run_dir = f"{args.run_base_dir}/width{args.cpu_width}/{benchmark.name}"
    dirs = [x for x in os.listdir(run_dir) if x.startswith(f"cpt.simpoint_{args.simpoint_num}")]
    assert len(dirs) == 1, f"Ensuring there is only one matching work_dir, matching dirs {dirs}"
    return dirs[0]

bm = [SysConfig(
    disks = [disk_image],
    rootdev = root_device,
    mem = mem_size,
    os_type = os_type
)]

#(TestCPUClass, test_mem_mode, FutureClass) = Simulation.setCPUClass(args)
# When fast-forwarding we restore into an atomic CPU, advance
# args.fast_forward_length instructions, then switch to the detailed O3 CPU
# for warmup + measurement (caches are flushed at the switch so warmup starts
# cold).  Two modes use this path:
#   * "ffrun"  always fast-forwards, restoring from the post-boot checkpoint.
#   * "simrun" fast-forwards only when --fast-forward-length > 0 (otherwise it
#              restores straight into the O3 CPU: the legacy SimPoint path).
ff_run = (args.mode == "ffrun")
fast_forward = ff_run or (args.mode == "simrun" and args.fast_forward_length > 0)
SwitchCPUClass = None
if fast_forward:
    (TestCPUClass, test_mem_mode) = Simulation.getCPUClass("X86AtomicSimpleCPU")
    (SwitchCPUClass, _) = Simulation.getCPUClass("X86O3CPU")
elif args.mode == "simrun":
    (TestCPUClass, test_mem_mode) = Simulation.getCPUClass("X86O3CPU")
else:
    (TestCPUClass, test_mem_mode) = Simulation.getCPUClass("X86AtomicSimpleCPU")



num_cpus = 1

ruby = False
cacheline_size = 64
sys_voltage = "3.0V"
sys_clock = "3GHz"
cpu_clock = "3GHz"

args.mem_type = "DDR4_2400_8x8"

if getattr(benchmark, "kind", "spec") == "pyperf":
    # pyperformance benchmark: run from the pre-built, offline venv tree in the
    # python disk image (/home/gem5/pyperf). The post-boot checkpoint is taken
    # at the leading "m5 checkpoint"; everything after it (interpreter startup +
    # the benchmark) is what the atomic CPU fast-forwards through before the O3
    # switch in ffrun mode.
    run_command = \
          "m5 checkpoint;\n"\
          "echo 'we have checkpointed';\n"\
          "cd /home/gem5/pyperf;\n"\
          f"echo 'Running pyperformance benchmark {benchmark.name}';\n"\
          f"./tool-venv/bin/python -m pyperformance run -b {benchmark.name} "\
          f"-o /home/gem5/pyperf/result_{benchmark.name}.json;\n"\
          "m5 exit;\n"
else:
    run_command = \
          "m5 checkpoint;\n"\
          "echo 'we have checkpointed';\n"\
          f"cd /home/gem5/x86-static-17/{benchmark.name};\n"\
          f"echo 'Running benchmark binary {benchmark.binary} with args {' '.join(benchmark.args[0])}';\n"\
          f"./{benchmark.binary} {' '.join(benchmark.args[0])};\n"\
          "m5 exit;\n"



#isa = ObjectList.cpu_list.get("AtomicSimpleCPU")
# Test system here
test_sys = makeLinuxX86System(
            test_mem_mode, num_cpus, bm[0], ruby, cmdline=kernel_cmd
        )


    # Set the cache line size for the entire system
test_sys.cache_line_size = cacheline_size

# Create a top-level voltage domain
test_sys.voltage_domain = VoltageDomain(voltage=sys_voltage)

# Create a source clock for the system and set the clock period
test_sys.clk_domain = SrcClockDomain(
    clock=sys_clock, voltage_domain=test_sys.voltage_domain
)

# Create a CPU voltage domain
test_sys.cpu_voltage_domain = VoltageDomain()

# Create a source clock for the CPUs and set the clock period
test_sys.cpu_clk_domain = SrcClockDomain(
    clock=cpu_clock, voltage_domain=test_sys.cpu_voltage_domain
)

test_sys.workload.object_file = binary(kernel)
if not args.mode == "simrun":
    work_dir = f"{args.run_base_dir}/width{args.cpu_width}/{benchmark.name}"
else:
    work_dir = f"{args.run_base_dir}/width{args.cpu_width}/{benchmark.name}/{get_sim_work_dir()}"


with open(f"{work_dir}/readfile.script", "w") as file:
    file.write(run_command)

test_sys.readfile = f"{work_dir}/readfile.script"


# For now, assign all the CPUs to the same clock domain
test_sys.cpu = [
    TestCPUClass(clk_domain=test_sys.cpu_clk_domain, cpu_id=i)
    for i in range(num_cpus)
]

bpClass = ObjectList.bp_list.get("MultiperspectivePerceptronTAGE64KB")
if not fast_forward:
    # In the fast-forward path the run CPU is atomic (no branch predictor);
    # the predictor is attached to the O3 switch CPUs instead (see below).
    test_sys.cpu[0].branchPred = bpClass()

# TODO: find out why Ruby is like this
if ruby:
    bootmem = getattr(test_sys, "_bootmem", None)
    Ruby.create_system(
        args, True, test_sys, test_sys.iobus, test_sys._dma_ports, bootmem
    )

    # Create a seperate clock domain for Ruby
    test_sys.ruby.clk_domain = SrcClockDomain(
        clock=args.ruby_clock, voltage_domain=test_sys.voltage_domain
    )

    # Connect the ruby io port to the PIO bus,
    # assuming that there is just one such port.
    test_sys.iobus.mem_side_ports = test_sys.ruby._io_port.in_ports

    for i, cpu in enumerate(test_sys.cpu):
        #
        # Tie the cpu ports to the correct ruby system ports
        #
        cpu.clk_domain = test_sys.cpu_clk_domain
        cpu.createThreads()
        cpu.createInterruptController()

        test_sys.ruby._cpu_ports[i].connectCpuPorts(cpu)

else:
    test_sys.iocache = IOCache(addr_ranges=test_sys.mem_ranges)
    test_sys.iocache.cpu_side = test_sys.iobus.mem_side_ports
    test_sys.iocache.mem_side = test_sys.membus.cpu_side_ports
    test_sys.cpu[0].createThreads()

    config_cache(test_sys)
    MemConfig.config_mem(args, test_sys)

if fast_forward:
    # Build the detailed O3 CPUs we switch in after the atomic fast-forward.
    # They share workload / clock / ISA with the atomic CPUs, start switched
    # out, and inherit the cache ports + architectural state via takeOverFrom
    # when m5.switchCpus() runs (so they need no cache/interrupt wiring here).
    test_sys.switch_cpus = [
        SwitchCPUClass(clk_domain=test_sys.cpu_clk_domain,
                       cpu_id=i, switched_out=True)
        for i in range(num_cpus)
    ]
    for i in range(num_cpus):
        # Do NOT set .system explicitly here: BaseCPU.system defaults to
        # Param.System(Parent.any), which resolves to test_sys because the
        # switch CPUs are children of it.  Assigning test_sys before Root()
        # exists would re-parent test_sys under the CPU (which is itself a
        # child of test_sys) and create a parent cycle -> RecursionError.
        test_sys.switch_cpus[i].workload = test_sys.cpu[i].workload
        test_sys.switch_cpus[i].clk_domain = test_sys.cpu[i].clk_domain
        test_sys.switch_cpus[i].isa = test_sys.cpu[i].isa
    test_sys.switch_cpus[0].branchPred = bpClass()
    for cpu in test_sys.switch_cpus:
        cpu.createThreads()
        configure_detailed_cpu(cpu)
    switch_cpu_list = [
        (test_sys.cpu[i], test_sys.switch_cpus[i]) for i in range(num_cpus)
    ]
elif args.mode == "simrun":
    # Legacy SimPoint path: the run CPU is the detailed O3 CPU, so apply the
    # detailed-core configuration directly to it.
    config_system(test_sys)
# Otherwise (cpt / profile / simtake) the run CPU is an atomic CPU, which has
# no O3 structures to configure (configure_detailed_cpu would touch fuPool etc.
# and fail), so we intentionally skip it here.

# Everything before was getting the system ready
# We now configure the run
# These are the four run-modes
checkpoint_post_kernel = False
simpoint_profile = False
simpoint_checkpoint = False
simpoint_run = False

if (args.mode == "cpt"):
    checkpoint_post_kernel = True
elif (args.mode == "profile"):
    simpoint_profile = True
elif (args.mode == "simtake"):
    simpoint_checkpoint = True
elif (args.mode == "simrun"):
    simpoint_run = True
elif (args.mode == "ffrun"):
    # ff_run already set above; restores the post-boot checkpoint, fast-forwards
    # in atomic, then switches to O3 for warmup + a fixed measured region.
    pass
else:
    print("Invalid operation mode selected, valid options are cpt, profile, simtake, simrun, ffrun")
    exit(1)

# These are control variables
simpoint_interval = 50000000
warmup_length     = 10000000
post_boot = False

if (checkpoint_post_kernel):
    post_boot = False
    cpt_dir = None
elif (simpoint_profile):
    post_boot = True
    cpt_dir = f"{checkpoints}/{benchmark.name}-cpt"
    simpoint_interval = 50000000
    test_sys.cpu[0].addSimPointProbe(simpoint_interval)
elif (simpoint_checkpoint):
    post_boot = True
    cpt_dir = f"{checkpoints}/{benchmark.name}-cpt"
    simpoint_interval = 50000000
elif (simpoint_run):
    post_boot = True
    cpts = [x for x in os.listdir(f"{simpoint_cpt_dir}/{benchmark.name}-cpt") if x.startswith(f"cpt.simpoint_{args.simpoint_num}")]
    assert(len(cpts) == 1)
    cpt_dir = f"{simpoint_cpt_dir}/{benchmark.name}-cpt/{cpts[0]}"

    # Measured-region length is fixed by the checkpoint geometry.
    simpoint_interval = int(cpts[0].split("_")[-3])

    # Detailed (O3) warmup length: honour an explicit override when given,
    # otherwise fall back to the value baked into the checkpoint name (legacy).
    if args.warmup_length >= 0:
        warmup_length = args.warmup_length
    else:
        warmup_length = int(cpts[0].split("_")[-1])

    if not fast_forward:
        # Legacy: O3 restores from the checkpoint, warms up, then measures.
        sim_start_insts = [warmup_length, warmup_length + simpoint_interval]
        test_sys.cpu[0].simpoint_start_insts = sim_start_insts
    # For the fast-forward path the warmup/measure markers are scheduled on the
    # O3 switch CPU *after* the switch (see the simpoint_run loop), and the
    # atomic CPU is stopped after the fast-forward window via max_insts below.

elif (ff_run):
    # Fast-forward run from the post-boot checkpoint: restore the (atomic)
    # post-boot checkpoint, let the benchmark run forward in atomic for
    # args.fast_forward_length instructions, switch to O3, then warm up and
    # measure a fixed region.  No SimPoint checkpoint / weights are involved.
    post_boot = True
    cpt_dir = f"{checkpoints}/{benchmark.name}-cpt"

    # Detailed (O3) warmup length: honour an explicit override, else 50M.
    if args.warmup_length >= 0:
        warmup_length = args.warmup_length
    else:
        warmup_length = 50000000

    # Measured-region length is an explicit CLI option for ffrun.
    measure_length = args.measure_length

    # The warmup/measure markers are scheduled on the O3 switch CPU *after* the
    # switch (see the ff_run block below); the atomic CPU is stopped after the
    # fast-forward window via max_insts below.


simpoints = []
if (simpoint_checkpoint):
    simpoints = parseSimpoints(benchmark, simpoint_interval,
                               warmup_length, test_sys)
    print("Prepped simpoints for running")


#if os.path.exists(checkpoint_dir):
#    shutil.rmtree(checkpoint_dir)

#os.mkdir(checkpoint_dir)
maxinsts = 100000000000

if fast_forward:
    # Stop the atomic CPU once the fast-forward window completes so we can
    # switch to the detailed O3 CPU for warmup + measurement.
    test_sys.cpu[0].max_insts_any_thread = args.fast_forward_length
else:
    test_sys.cpu[0].max_insts_any_thread = maxinsts

root = Root(full_system=True, system=test_sys)

m5.instantiate(cpt_dir)
checkpoint_dir = f"{checkpoints}"

stat_root_simobjs = []
stats_root = []
for stat_root_str in stats_root:
    stat_root_simobjs.extend(root.get_simobj(stat_root_str))
m5.stats.global_dump_roots = stat_root_simobjs


#if options.checkpoint_restore != None and maxtick < cpt_starttick:
#    fatal(
#        "Bad maxtick (%d) specified: "
#        "Checkpoint starts starts from tick: %d",
#        maxtick,
#        cpt_starttick,
#    )

print("**** REAL SIMULATION ****")

if (checkpoint_post_kernel):
    # cpt mode (the only mode with post_boot == False): boot from scratch,
    # skip the "kernel booted" m5_exit raised by after_boot.sh, and take the
    # post-boot checkpoint when the run script's leading `m5 checkpoint` fires
    # (just before the benchmark itself starts). We then stop without running
    # the benchmark.
    while True:
        exit_event = m5.simulate()
        cause = exit_event.getCause()
        print(f"Exit event encountered, cause = {cause}")
        if cause == "checkpoint":
            cpt_out = joinpath(m5.options.outdir, f"{benchmark.name}-cpt")
            m5.checkpoint(cpt_out)
            print(f"Post-boot checkpoint written to {cpt_out}")
            break
        elif cause == "m5_exit instruction encountered":
            print("(kernel-boot / bridge exit; continuing to the run script)")
            continue
        else:
            print(f"Unexpected exit before checkpoint ({cause}); aborting cpt.")
            break

elif (simpoint_profile):
    exit_event = m5.simulate()
    print(f"Exit event encountered, cause = {exit_event.getCause()}")

elif (simpoint_checkpoint):
    num_checkpoints = 0
    index = 0
    last_cpt = -1 
    for simpoint in simpoints:
        interval, weight, starting_inst_count, warmup_length = simpoint
        print(f"Running to checkpoint {index} with start {starting_inst_count} as first inst")
        
        if (starting_inst_count == last_cpt):
            print("simpoints right next to each other, exiting")
            exit(1)
        
        exit_event = m5.simulate()
        print(f"Exit event encountered, cause = {exit_event.getCause()}")
        assert exit_event.getCause() == "simpoint starting point found", "Exit cause should only be due to meeting a simpoint"

        m5.checkpoint(
            f"{cpt_dir}/cpt.simpoint_{index}_inst_{starting_inst_count}_weight_{weight}_interval_{simpoint_interval}_warmup_{warmup_length}"
        )
        print(
            f"Checkpoint #{index} written, start-inst: {starting_inst_count}, weight: {weight}"
        )

        last_cpt = starting_inst_count
        num_checkpoints += 1
        index += 1

    print(f"Exiting @ tick {m5.curTick()} because {exit_event}")
    print(f"{num_checkpoints} checkpoints taken")

elif (simpoint_run):
    if fast_forward:
        # Phase 1: atomic fast-forward of args.fast_forward_length instructions.
        exit_event = m5.simulate()
        print(f"Fast-forward complete, cause = {exit_event.getCause()}")

        # Switch to the detailed O3 CPU, then flush the caches so the detailed
        # warmup begins from a cold microarchitecture (cold caches; the freshly
        # switched-in O3 also brings a cold pipeline, TLBs and predictor).
        m5.switchCpus(test_sys, switch_cpu_list)
        m5.memWriteback(test_sys)
        m5.memInvalidate(test_sys)

        # Schedule warmup-end and measure-end relative to the live (post-switch)
        # instruction count, so the markers are robust to the count handed over
        # from the atomic CPU.
        test_sys.switch_cpus[0].scheduleSimpointsInstStop(
            [warmup_length, warmup_length + simpoint_interval]
        )

    exit_event = m5.simulate()
    assert(exit_event.getCause() == "simpoint starting point found")
    print("Warmed up! Dumping and resetting stats!")
    m5.stats.dump()
    m5.stats.reset()
    exit_event = m5.simulate()
    if (exit_event.getCause() == "simpoint starting point found"):
        print("Done running SimPoint!")
        sys.exit(exit_event.getCode())
    print(f"Abnormal exit event encountered, cause = {exit_event.getCause()}")

elif (ff_run):
    # Phase 1: atomic fast-forward of args.fast_forward_length instructions
    # (the atomic CPU is stopped by max_insts_any_thread set above).
    exit_event = m5.simulate()
    print(f"Fast-forward complete, cause = {exit_event.getCause()}")
    if exit_event.getCause() == "m5_exit instruction encountered":
        # The benchmark finished before we reached the fast-forward target:
        # the requested skip is longer than the whole workload. Lower
        # --fast-forward-length (or profile the benchmark length first).
        print("Benchmark exited during fast-forward; nothing to measure. "
              "Reduce --fast-forward-length.")
        sys.exit(0)

    # Switch to the detailed O3 CPU, then flush the caches so the detailed
    # warmup begins from a cold microarchitecture (cold caches, pipeline,
    # TLBs and predictor).
    m5.switchCpus(test_sys, switch_cpu_list)
    m5.memWriteback(test_sys)
    m5.memInvalidate(test_sys)

    # Schedule warmup-end and measure-end relative to the live (post-switch)
    # instruction count.
    test_sys.switch_cpus[0].scheduleSimpointsInstStop(
        [warmup_length, warmup_length + measure_length]
    )

    exit_event = m5.simulate()
    if exit_event.getCause() != "simpoint starting point found":
        print(f"Benchmark exited during O3 warmup, cause = "
              f"{exit_event.getCause()}. Reduce --warmup-length / "
              f"--fast-forward-length.")
        sys.exit(0)
    print("Warmed up! Dumping and resetting stats!")
    m5.stats.dump()
    m5.stats.reset()

    exit_event = m5.simulate()
    if exit_event.getCause() == "simpoint starting point found":
        print("Done running measured region!")
        sys.exit(exit_event.getCode())
    # Benchmark finished before the full measured region: stats are still valid
    # for the (shorter) region actually executed.
    print(f"Measured region ended early, cause = {exit_event.getCause()}")
    m5.stats.dump()
    sys.exit(0)
