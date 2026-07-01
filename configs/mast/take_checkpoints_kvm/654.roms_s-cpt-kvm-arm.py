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

binary_path = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/654.roms_s/run/run_base_refspeed_arm-build-64.0000/sroms_base.arm-build-64"
benchmark_binary = BinaryResource(local_path=binary_path)

benchmark_arguments = [
]

simpoint_list = [
    2,
    1,
    0,
]

simpoint_weights = [
    0.333333,
    0.333333,
    0.333333,
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
