import argparse
from pathlib import Path

import m5

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
from gem5.components.processors.simple_switchable_processor import (
    SimpleSwitchableProcessor,
)
from gem5.simulate.simulator import Simulator
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.exit_event_generators import (
    save_checkpoint_generator,
    switch_generator,
)

requires(isa_required=ISA.ARM, kvm_required=True)

parser = argparse.ArgumentParser()

parser.add_argument(
    "--checkpoint-path",
    type=str,
    required=False,
    default="se_checkpoint_folder/",
    help="Directory to store checkpoints (use a warmup-specific path per run).",
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

processor = SimpleSwitchableProcessor(
    starting_core_type=CPUTypes.KVM,
    switch_core_type=CPUTypes.ATOMIC,
    isa=ISA.ARM,
    num_cores=1,
)

board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

binary_path = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/638.imagick_s/run/run_base_refspeed_arm-build-64.0000/imagevalidate_638_base.arm-build-64"
benchmark_binary = BinaryResource(local_path=binary_path)

benchmark_arguments = [
    '-limit',
    'disk',
    0,
    '/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/638.imagick_s/run/run_base_refspeed_arm-build-64.0000/refspeed_input.tga',
    '-resize',
    '817%',
    '-rotate',
    -2.76,
    '-shave',
    '540x375',
    '-alpha',
    'remove',
    '-auto-level',
    '-contrast-stretch',
    '1x1%',
    '-colorspace',
    'Lab',
    '-channel',
    'R',
    '-equalize',
    '+channel',
    '-colorspace',
    'sRGB',
    '-define',
    'histogram:unique-colors=false',
    '-adaptive-blur',
    '0x5',
    '-despeckle',
    '-auto-gamma',
    '-adaptive-sharpen',
    55,
    '-enhance',
    '-brightness-contrast',
    '10x10',
    '-resize',
    '30%',
    '/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/638.imagick_s/run/run_base_refspeed_arm-build-64.0000/refspeed_output.tga',
]

simpoint_list = [
    10277,
    44702,
    42228,
    5391,
    33471,
    229,
    42848,
    42690,
    39300,
    7128,
    19156,
    15732,
    9448,
]

simpoint_weights = [
    0.0599661,
    0.0114497,
    0.00708367,
    0.11942,
    0.317807,
    0.000267308,
    0.0513009,
    0.0550432,
    0.216809,
    0.018422,
    0.00289584,
    0.0523033,
    0.0872316,
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

checkpoint_dir = Path(args.checkpoint_path)

simulator = Simulator(
    board=board,
    on_exit_event={
        ExitEvent.SIMPOINT_BEGIN: save_checkpoint_generator(checkpoint_dir),
        ExitEvent.SWITCHCPU: switch_generator(processor=processor),
    },
)

m5.stats.reset()
simulator.run()
