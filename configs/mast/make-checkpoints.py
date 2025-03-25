import argparse
import m5

from gem5.components.boards.x86_board import X86Board
from gem5.components.cachehierarchies.ruby.mesi_two_level_cache_hierarchy import MESITwoLevelCacheHierarchy
from gem5.components.memory import DIMM_DDR5_4400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.utils.requires import requires
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator
from gem5.resources.resource import (
    DiskImageResource,
    obtain_resource
)

from benchmarks import ALL_BENCHMARKS

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

# Run a check to ensure the right version of gem5 is being used.
requires(isa_required=ISA.X86)

# Setup the cache hierarchy.
# For classic, PrivateL1PrivateL2 and NoCache have been tested.
# For Ruby, MESI_Two_Level and MI_example have been tested.
#cache_hierarchy = MESIThreeLevelCacheHierarchy(
cache_hierarchy = MESITwoLevelCacheHierarchy(
    l1d_size="32KiB",
    l1d_assoc=8,
    l1i_size="32KiB",
    l1i_assoc=8,
    l2_size="2MiB",
    l2_assoc=16,
    num_l2_banks=2
#    l3_size="16MiB",
#    l3_assoc=20
)


# Setup the system memory.
memory = DIMM_DDR5_4400(size="12GiB")

# Setup a single core Processor.
processor = SimpleProcessor(
    cpu_type=CPUTypes.ATOMIC,
    isa=ISA.X86,
    num_cores=1
)

# Setup the board.
board = X86Board(
    clk_freq="3.5GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

command = "m5 checkpoint;"\
          "echo 'we have checkpointed';"\
          "m5 exit;"\
          f"cd /home/gem5/x86-static-17/{benchmark.name};"\
          f"./{benchmark.binary} {' '.join(benchmark.args[0])};"\
          "m5 exit;"
          

board.set_kernel_disk_workload(
    kernel=obtain_resource(resource_id="x86-linux-kernel-5.4.0-105-generic"),
    disk_image=DiskImageResource("/cluster/home/amundbk/mast/full_system/x86-ubuntu"),
    kernel_args=[
            "earlyprintk=ttyS0",
            "console=ttyS0",
            "lpj=7999923",
            "root=/dev/sda2",
            "no_systemd=true"
        ],
    #use readfile to specify a file for this, do programatically for spec17
    readfile_contents=command
)

#board.processor.cores[0].core.addSimPointProbe(100000)

def exit_event_handler():
    print("Exit Event: Kernel Booted")
    yield False
    print("Exit Event: Post-Boot")
    m5.stats.reset()
    yield False
    print("Exit Event: Post Runscript")
    yield True


sim = Simulator(board=board,
                on_exit_event={
                    ExitEvent.EXIT: exit_event_handler()
})


sim.run()

print(
    "Exiting @ tick {} because {}.".format(
        sim.get_current_tick(), sim.get_last_exit_event_cause()
    )
)
