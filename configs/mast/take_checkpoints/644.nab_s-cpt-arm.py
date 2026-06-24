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

binary_path = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/644.nab_s/run/run_base_refspeed_arm-build-64.0000/nab_s_base.arm-build-64"
benchmark_binary = BinaryResource(local_path=binary_path)

benchmark_arguments = [
    '/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/644.nab_s/run/run_base_refspeed_arm-build-64.0000/3j1n',
    20140317,
    220,
]

simpoint_list = [
    14598,
    18216,
    16280,
    10268,
    1471,
    5241,
    6088,
    9762,
    679,
    9424,
    18121,
    18214,
    3401,
]

simpoint_weights = [
    0.0207099,
    0.00962113,
    0.0746861,
    0.0114149,
    0.153232,
    0.0181008,
    0.0638148,
    0.255259,
    0.0901777,
    0.0315269,
    0.072838,
    0.0424526,
    0.156167,
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
