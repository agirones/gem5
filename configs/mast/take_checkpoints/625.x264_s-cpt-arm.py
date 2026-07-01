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

parser.add_argument(
    "--warmup-interval",
    type=int,
    default=50000000,
    help="Instructions of warmup before each simpoint ROI; checkpoint is taken at warmup start.",
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

binary_path = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/625.x264_s/run/run_base_refspeed_arm-build-64.0000/imagevalidate_625_base.arm-build-64"
benchmark_binary = BinaryResource(local_path=binary_path)

benchmark_arguments = [
    '--pass',
    1,
    '--stats',
    '/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/625.x264_s/run/run_base_refspeed_arm-build-64.0000/x264_stats.log',
    '--bitrate',
    1000,
    '--frames',
    1000,
    '-o',
    '/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/625.x264_s/run/run_base_refspeed_arm-build-64.0000/BuckBunny_New.264',
    '/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/625.x264_s/run/run_base_refspeed_arm-build-64.0000/BuckBunny.yuv',
    '1280x720',
]

simpoint_list = [
    21491,
    8758,
    11966,
    10392,
    19355,
    17736,
    17298,
    5987,
    559,
    9915,
    15167,
    15198,
    5800,
]

simpoint_weights = [
    0.202828,
    0.0412707,
    0.083576,
    0.0206928,
    0.02874,
    0.0463673,
    0.0656806,
    0.169681,
    0.0457158,
    0.0391248,
    0.0206545,
    0.0326487,
    0.20302,
]

board.set_se_simpoint_workload(
    binary=benchmark_binary,
    arguments=benchmark_arguments,
    simpoint=SimpointResource(
        simpoint_interval=10000000,
        simpoint_list=simpoint_list,
        weight_list=simpoint_weights,
        warmup_interval=args.warmup_interval,
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
