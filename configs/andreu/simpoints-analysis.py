import time
import m5
import argparse
import os
import logging

from gem5.components.boards.x86_board import X86Board
from gem5.components.cachehierarchies.classic.no_cache import NoCache
from gem5.components.memory.single_channel import SingleChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_switchable_processor import (
    SimpleSwitchableProcessor,
)
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import obtain_resource
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires

# Check requirements
requires(
    isa_required=ISA.X86,
)

sizes = ['test', 'train', 'ref']

parser = argparse.ArgumentParser()
parser.add_argument("--benchmark", required=True, help="Benchmark to run")
parser.add_argument("--size", default='ref', choices=sizes, help="Benchmark size to run")
parser.add_argument("--interval", required=False, default=10_000_000, help="Simpoints interval")
args = parser.parse_args()

cache_hierarchy = NoCache()

memory = SingleChannelDDR4_2400(size="12GiB")

processor = SimpleSwitchableProcessor(
    starting_core_type=CPUTypes.KVM,
    switch_core_type=CPUTypes.ATOMIC,
    isa=ISA.X86,
    num_cores=1,
)

for proc in processor.start:
    proc.core.usePerf = False

all_cores_list = list(processor._all_cores())
all_cores_list[1].core.addSimPointProbe(args.interval)

output_dir = "speclogs_" + "".join(x.strip() for x in time.asctime().split())
output_dir = output_dir.replace(":", "")

try:
    os.makedirs(os.path.join(m5.options.outdir, output_dir))
except FileExistsError:
    logging.warning("spec output directory already exists!")

command = f"{args.benchmark} {args.size} {output_dir}"

board = X86Board(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# Set workload based on benchmark selection
workload = obtain_resource(f"x86-ubuntu-24.04-boot-with-systemd")
workload.set_parameter('readfile_contents', command)
board.set_workload(
    workload=workload,
)

def handle_exit():
    print("Done bootling Linux")
    print(f"Num of instructions so far: {int(simulator.get_stats()['simInsts']['value'])}")
    print()
    yield False
    print("Second exit: workload read")
    print(f"Num of instructions so far: {int(simulator.get_stats()['simInsts']['value'])}")
    print()
    processor.switch()
    m5.stats.reset()
    yield False
    print("Benchmark finished")
    print(f"Num of instructions so far: {int(simulator.get_stats()['simInsts']['value'])}")
    m5.stats.dump()
    yield True

simulator = Simulator(
    board=board,
    on_exit_event={
        ExitEvent.EXIT: handle_exit()
    },
)

# We maintain the wall clock time.

globalStart = time.time()

print("Running the simulation")
print("Using KVM cpu")

m5.stats.reset()

# We start the simulation
simulator.run()

# We print the final simulation statistics.

print("Done with the simulation")
