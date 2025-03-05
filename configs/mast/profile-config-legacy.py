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

args = parser.parse_args()


benchmark = ALL_BENCHMARKS[args.benchmark_num]

script_dir = os.path.dirname(__file__)
root = os.path.abspath(f"{script_dir}/../..")
print(root)
checkpoints = f"{root}/runs/legacy-checkpoints"

disk_image = "/cluster/home/amundbk/mast/full_system/x86-ubuntu"
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

kernel = "/cluster/home/amundbk/.cache/gem5/x86-linux-kernel-5.4.0-105-generic"


#test_sys.init_param = args.init_param
def config_cache(system):

    dcache_class, icache_class, l2_cache_class, walk_cache_class = (
        L1_DCache,
        L1_ICache,
        L2Cache,
        None
    )

    system.cache_line_size = cacheline_size

    l2_config = dict(
        clk_domain=system.cpu_clk_domain,
        size="2MiB",
        assoc="16"
    )

    l1i_config = dict(
        size="32KiB",
        assoc="8"
    )

    l1d_config = dict(
        size="32KiB",
        assoc="8"
    )

    system.l2 = l2_cache_class(**l2_config)

    system.tol2bus = L2XBar(clk_domain=system.cpu_clk_domain)
    system.l2.cpu_side = system.tol2bus.mem_side_ports
    system.l2.mem_side = system.membus.cpu_side_ports

    icache = icache_class(**l1i_config)
    dcache = dcache_class(**l1d_config)

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

bm = [SysConfig(
    disks = [disk_image],
    rootdev = root_device,
    mem = mem_size,
    os_type = os_type
)]

#(TestCPUClass, test_mem_mode, FutureClass) = Simulation.setCPUClass(args)

(TestCPUClass, test_mem_mode) = Simulation.getCPUClass("X86NonCachingSimpleCPU")
#test_mem_mode = "atomic"
FutureClass = TestCPUClass


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
work_dir = f"{root}/runs/{benchmark.name}"


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
IndirectBPClass = ObjectList.indirect_bp_list.get(
    "SimpleIndirectPredictor"
)
test_sys.cpu[0].branchPred.indirectBranchPred = (
    IndirectBPClass()
)

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

root = Root(full_system=True, system=test_sys)

# Everything before was getting the system ready
# We now configure the run
# These are the three run-modes
checkpoint_post_kernel = False
simpoint_profile = True
simpoint_checkpoint = False

# These are control variables
simpoint_interval = 50000000
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

m5.instantiate(cpt_dir)
checkpoint_dir = f"{checkpoints}"

#if os.path.exists(checkpoint_dir):
#    shutil.rmtree(checkpoint_dir)

#os.mkdir(checkpoint_dir)

maxinsts = 100000000000

test_sys.cpu[0].max_insts_any_thread = maxinsts

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
exit_event = m5.simulate()
print(f"Exit event encountered, cause = {exit_event.getCause()}")

if (not post_boot):
    if (exit_event.getCause() == "m5_exit instruction encountered"):
        print("Kernel booted most likely, we go back in")
        exit_event = m5.simulate()
    print(f"Exit event encountered, cause = {exit_event.getCause()}")
    if (exit_event.getCause() == "m5_exit instruction encountered"):
        print("We should be post-boot now. Resetting stats\n"\
            "Should be running runscript now")
        m5.stats.reset()
        exit_event = m5.simulate()
print(f"Exit event encountered, cause = {exit_event.getCause()}")
if (exit_event.getCause() == "checkpoint"):
    assert(checkpoint_post_kernel)
    m5.checkpoint(joinpath(m5.options.outdir, f"{benchmark.name}-cpt"))
