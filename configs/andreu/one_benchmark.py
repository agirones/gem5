import m5
import argparse
import sys
from multiprocessing import Process
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.private_l1_private_l2_walk_cache_hierarchy import (
    PrivateL1PrivateL2WalkCacheHierarchy
)
from gem5.components.processors.simple_switchable_processor import (
    SimpleSwitchableProcessor,
)
from gem5.components.memory import SingleChannelDDR3_1600
from gem5.components.processors.cpu_types import CPUTypes
from gem5.isas import ISA
from gem5.utils.requires import requires
from gem5.simulate.simulator import Simulator
from gem5.simulate.exit_event import ExitEvent
from gem5.resources.resource import (
    BinaryResource
)

#binary_path = "benchmarks/spec/cpu2017/run_benchmark"
binary_path = "/cluster/home/andreug/research/gem5/gem5/benchmarks/spec/cpu2017/benchspec/CPU/605.mcf_s/run/run_base_refspeed_static-17-m64.0000/mcf_s_base.static-17-m64"
simulated_cwd = "/cluster/home/andreug/research/gem5/gem5/benchmarks/spec/cpu2017/benchspec/CPU/605.mcf_s/run/run_base_refspeed_static-17-m64.0000/"

parser = argparse.ArgumentParser()
parser.add_argument("--bench", type=str, default="")
parser.add_argument("--comm", type=str, default="")

args = parser.parse_args()

benchmark = args.bench
command = args.comm

#RUN_DIR = "/cluster/home/amundbk/ShadowBinding/gem5/runs"
#SPEC06_PATH = "/cluster/home/amundbk/gem5/dom/x86-spec-static-ref"
#CONFIG_DIR="/cluster/home/amundbk/ShadowBinding/gem5/configs/shadowbinding"

# Run a check to ensure the right version of gem5 is being used.
requires(isa_required=ISA.X86)

# Setup the cache hierarchy.
# For classic, PrivateL1PrivateL2 and NoCache have been tested.
# For Ruby, MESI_Two_Level and MI_example have been tested.
cache_hierarchy = PrivateL1PrivateL2WalkCacheHierarchy(
    l1d_size="64KiB",
#    l1d_assoc=8,
    l1i_size="32KiB",
#    l1i_assoc=4,
    l2_size="2MiB",
#    l2_assoc=16
)


# Setup the system memory.
memory = SingleChannelDDR3_1600(size="16GiB")

# Setup a single core Processor.
processor = SimpleSwitchableProcessor(
    starting_core_type=CPUTypes.ATOMIC,
    switch_core_type=CPUTypes.O3,
    isa=ISA.X86,
    num_cores=1
)

# Setup the board.
board = SimpleBoard(
    clk_freq="2GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# Binary resource
binary = BinaryResource(local_path=binary_path)

# Set the binary workload
board.set_se_binary_workload(
    binary=binary,
    arguments=[simulated_cwd + "inp.in"]
)


def max_inst():
    print("Processor switch initiated, resetting stats")
    processor.switch()
    m5.stats.reset()
    sim.schedule_max_insts(10**9)
    yield False
    print("Detailed simulation complete, dumping stats")
    m5.stats.dump()
    yield True
    

sim = Simulator(
    board=board, 
    full_system=False,
    on_exit_event={ExitEvent.MAX_INSTS: max_inst()}
)

sim.schedule_max_insts(10**10)

sim.run()

print(
    "Exiting @ tick {} because {}.".format(
        sim.get_current_tick(), sim.get_last_exit_event_cause()
    )
)
