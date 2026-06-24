import argparse
from pathlib import Path

from gem5.isas import ISA
from gem5.utils.requires import requires
from gem5.resources.resource import (
    SimpointResource,
    BinaryResource,
)
from gem5.components.memory import SingleChannelDDR3_1600
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.no_cache import NoCache
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.simulate.simulator import Simulator
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.exit_event_generators import save_checkpoint_generator

requires(isa_required=ISA.ARM)

parser = argparse.ArgumentParser()

parser.add_argument(
    "--checkpoint-path",
    type=str,
    required=False,
    default="se_checkpoint_folder/",
    help="The directory to store the checkpoint.",
)

args = parser.parse_args()

cache_hierarchy = NoCache()
memory = SingleChannelDDR3_1600(size="16GiB")

processor = SimpleProcessor(cpu_type=CPUTypes.ATOMIC, isa=ISA.ARM, num_cores=1)

board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

binary_path = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/600.perlbench_s/run/run_base_refspeed_arm-build-64.0000/perlbench_s_base.arm-build-64"
benchmark_binary = BinaryResource(local_path=binary_path)

checkspam_pl_file = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/600.perlbench_s/run/run_base_refspeed_arm-build-64.0000/checkspam.pl"
lib_path = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/600.perlbench_s/run/run_base_refspeed_arm-build-64.0000/lib"
benchmark_arguments = [f"-I{lib_path}", checkspam_pl_file, 2500, 5, 25, 11, 150, 1, 1, 1, 1]

simpoint_list = [
    97868,
    112234,
    69913,
    57785,
    84336,
    131949,
    33656,
    6690,
    101914,
    30122,
    70909,
    90783,
    55878,
]

simpoint_weights = [
    0.141562,
    0.137796,
    0.0906971,
    0.0565717,
    0.0835926,
    0.0563364,
    0.0258735,
    0.0417522,
    0.105267,
    0.176548,
    0.0125911,
    0.0599034,
    0.01151,
]

board.set_se_simpoint_workload(
    binary=benchmark_binary,
    arguments=benchmark_arguments,
    simpoint=SimpointResource(
        simpoint_interval=10000000,
        simpoint_list=simpoint_list,
        weight_list=simpoint_weights,
        warmup_interval=10000000,
    ),
)

dir = Path(args.checkpoint_path)

simulator = Simulator(
    board=board,
    on_exit_event={
        ExitEvent.SIMPOINT_BEGIN: save_checkpoint_generator(dir)
    },
)

simulator.run()