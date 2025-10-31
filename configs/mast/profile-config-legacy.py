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

addToPath("../")

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
    "--run-base-dir", type=str,
    default="_default_run_dir_runs",
    help="Base directory for simulation runs (e.g., 'my_sims' or 'data/runs')"
)

args = parser.parse_args()

benchmark = ALL_BENCHMARKS[args.benchmark_num]

script_dir = os.path.dirname(__file__)
root = os.path.abspath(f"{script_dir}/../..")

if args.run_base_dir == "_default_run_dir_runs":
    args.run_base_dir = f"{root}/runs/output"

checkpoints = f"{root}/runs/legacy-checkpoints"
simpoints_dir = f"/cluster/projects/mast/simpoints/simpoints"
simpoint_cpt_dir = "/cluster/projects/mast/checkpoints/simpoint-checkpoints"

disk_image = "/cluster/projects/mast/full-system/disk-images/x86-ubuntu-with-spec17"
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

kernel = "/cluster/projects/mast/full-system/kernels/x86-linux-kernel-5.4.0-105-generic"


def config_system(system):
    for cpu in system.cpu:
#        for fupool in cpu.fuPool.FUList:
#            fupool.count = 8
        
        fu_list = cpu.fuPool.FUList[0].count = 5
        fu_list = cpu.fuPool.FUList[1].count = 3
        fu_list = cpu.fuPool.FUList[4].count = 3
        fu_list = cpu.fuPool.FUList[5].count = 2
        fu_list = cpu.fuPool.FUList[7].count = 2
        fu_list = cpu.fuPool.FUList[8].count = 0

        cpu.fetchWidth = args.cpu_width
        cpu.decodeWidth = args.cpu_width
        cpu.renameWidth = args.cpu_width
        cpu.dispatchWidth = args.cpu_width
        cpu.issueWidth = args.cpu_width
        cpu.wbWidth = 12
        cpu.commitWidth = args.cpu_width

        cpu.numIQEntries = 205
        cpu.numPhysFloatRegs = 332
        cpu.numPhysIntRegs = 280
        cpu.numROBEntries = 512
        cpu.LQEntries = 192
        cpu.SQEntries = 114

        cpu.backComSize = 30
        cpu.forwardComSize = 512


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
        tag_latency="1",
        data_latency="1",
#        tag_latency="4",
#        data_latency="4",
    )

    l1d_config = dict(
        size="48KiB",
        assoc="12",
        tag_latency="1",
        data_latency="1",
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
if not args.mode == "simrun":
    (TestCPUClass, test_mem_mode) = Simulation.getCPUClass("X86AtomicSimpleCPU")
else:
    (TestCPUClass, test_mem_mode) = Simulation.getCPUClass("X86O3CPU")



num_cpus = 1

ruby = False
cacheline_size = 64
sys_voltage = "3.0V"
sys_clock = "3GHz"
cpu_clock = "3GHz"

args.mem_type = "DDR4_2400_8x8"

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

config_system(test_sys)

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
else:
    print("Invalid operation mode selected, valid options are cpt, profile, simtake, simrun")
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
    warmup_length = cpts[0].split("_")[-1]
    simpoint_interval = cpts[0].split("_")[-3]

    sim_start_insts = []
    sim_start_insts.append(warmup_length)
    sim_start_insts.append(str(int(warmup_length)+int(simpoint_interval)))
    test_sys.cpu[0].simpoint_start_insts = sim_start_insts


simpoints = []
if (simpoint_checkpoint):
    simpoints = parseSimpoints(benchmark, simpoint_interval,
                               warmup_length, test_sys)
    print("Prepped simpoints for running")


#if os.path.exists(checkpoint_dir):
#    shutil.rmtree(checkpoint_dir)

#os.mkdir(checkpoint_dir)
maxinsts = 100000000000

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

if (not post_boot):
    exit_event = m5.simulate()
    print(f"Exit event encountered, cause = {exit_event.getCause()}")
    if (exit_event.getCause() == "m5_exit instruction encountered"):
        print("Kernel booted most likely, we go back in")
        exit_event = m5.simulate()
    print(f"Exit event encountered, cause = {exit_event.getCause()}")
    if (exit_event.getCause() == "m5_exit instruction encountered"):
        print("We should be post-boot now. Resetting stats\n"\
            "Should be running runscript now")
        m5.stats.reset()
        exit_event = m5.simulate()

if (checkpoint_post_kernel):
    exit_event = m5.simulate()
    print(f"Exit event encountered, cause = {exit_event.getCause()}")
    if (exit_event.getCause() == "checkpoint"):
        assert checkpoint_post_kernel, "checkpoint event encountered, but not in that mode"
        m5.checkpoint(joinpath(m5.options.outdir, f"{benchmark.name}-cpt"))

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
