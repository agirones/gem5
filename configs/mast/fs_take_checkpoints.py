"""
ARM full-system SimPoint checkpoint taking with KVM fast-forward.

Boots an Ubuntu disk image on ArmBoard, fast-forwards with KVM (Linux perf
instruction counting), and takes checkpoints at each SimPoint warmup start.
SimPoints are scheduled at the guest m5 workbegin so KVM inst counts align
with Valgrind BBV (benchmark-relative intervals).

Example:
    build/ARM/gem5.opt configs/mast/fs_take_checkpoints.py \\
        --benchmark 998.specrand_is \\
        --disk-image /path/to/arm-ubuntu-spec2017.img \\
        --checkpoint-path /path/to/out
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Generator, Optional

import m5
from m5.objects import (
    ArmDefaultRelease,
    BaseCPU,
    VExpress_GEM5_V1,
)
from gem5.components.cachehierarchies.classic.private_l1_private_l2_cache_hierarchy import (
    PrivateL1PrivateL2CacheHierarchy,
)
from gem5.components.boards.arm_board import ArmBoard
from gem5.components.memory import DualChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import (
    CheckpointResource,
    DiskImageResource,
    SimpointResource,
    obtain_resource,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires

from fs_spec_common import (
    DEFAULT_WARMUP_INTERVAL,
    FS_GUEST_MEMORY_SIZE,
    SIMPOINT_INTERVAL,
    attach_kvm_pmu,
    boot_aware_exit_end_handler,
    build_readfile_contents,
    ensure_exit_on_work_items_after_checkpoint_restore,
    fs_simpoint_checkpoint_generator,
    load_simpoints,
    project_root_from_config,
    register_continue_after_readfile_bridge,
)

requires(isa_required=ISA.ARM, kvm_required=True)


def fs_workbegin_handler(
    kvm_cpu: BaseCPU,
    simpoint_start_insts: list[int],
) -> Generator[Optional[bool], None, None]:
    """Schedule SimPoints at m5 workbegin (benchmark start, not boot shell)."""
    scheduled = False
    while True:
        if not scheduled:
            base = kvm_cpu.totalInsts()
            adjusted = [base + inst for inst in simpoint_start_insts]
            print(
                "Post-boot m5 workbegin: scheduling "
                f"{len(adjusted)} KVM SimPoints from inst offset {base:,}"
            )
            kvm_cpu.scheduleSimpointsInstStop(sorted(set(adjusted)))
            scheduled = True
            m5.stats.reset()
        yield False


def fs_exit_end_handler(
    kvm_cpu: BaseCPU,
    boot_checkpoint_used: bool,
    simpoint_start_insts: list[int] | None = None,
) -> Generator[Optional[bool], None, None]:
    """Final m5 exit ends the SimPoint checkpoint run."""

    def _schedule_simpoints(cpu: BaseCPU, _insts: int) -> None:
        base = cpu.totalInsts()
        adjusted = [base + inst for inst in simpoint_start_insts or []]
        print(
            "Post-sync m5 exit: scheduling "
            f"{len(adjusted)} KVM SimPoints from inst offset {base:,}"
        )
        cpu.scheduleSimpointsInstStop(sorted(set(adjusted)))
        m5.stats.reset()

    on_sync = _schedule_simpoints if boot_checkpoint_used else None
    yield from boot_aware_exit_end_handler(
        kvm_cpu,
        boot_checkpoint_used=boot_checkpoint_used,
        on_post_sync=on_sync,
    )


def _resolve_path(path: str) -> str:
    if path[0] != "/":
        return os.path.abspath(path)
    return path


def _ensure_kvm_perf(processor: SimpleProcessor) -> None:
    """KVM SimPoint stops require Linux perf, user-mode instruction counting."""
    for core in processor.get_cores():
        cpu = core.get_simobject()
        if hasattr(cpu, "usePerf"):
            cpu.usePerf = True
        if hasattr(cpu, "perfExcludeKernel"):
            cpu.perfExcludeKernel = True


def build_parser(default_benchmark: str | None = None) -> argparse.ArgumentParser:
    project_root = project_root_from_config()
    default_disk = project_root / "fs_disk_images/arm-ubuntu-spec2017-fpspeed.img"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark",
        type=str,
        default=default_benchmark,
        required=default_benchmark is None,
        help="SPEC CPU2017 fpspeed benchmark name (e.g. 998.specrand_is)",
    )
    parser.add_argument(
        "--disk-image",
        type=str,
        default=str(default_disk),
        help="Full path to the ARM Ubuntu disk image with SPEC installed",
    )
    parser.add_argument(
        "--partition",
        type=str,
        default="2",
        help="Root partition on the disk image (NPB image uses partition 2)",
    )
    parser.add_argument(
        "--boot-checkpoint",
        type=str,
        default=None,
        help="Optional post-boot checkpoint to restore (skip KVM OS boot)",
    )
    parser.add_argument(
        "--checkpoint-path",
        type=str,
        default="fs_checkpoint_folder/",
        help="Directory to store SimPoint checkpoints",
    )
    parser.add_argument(
        "--warmup-interval",
        type=int,
        default=DEFAULT_WARMUP_INTERVAL,
        help="Warmup instructions before each SimPoint ROI",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=str(project_root),
        help="Microbenchmarks repo root (for simpoints and valgrind jobs)",
    )
    parser.add_argument(
        "--num-cores",
        type=int,
        default=1,
        help="Number of CPU cores (must match boot checkpoint if used)",
    )
    parser.add_argument(
        "--resource-directory",
        type=str,
        default=None,
        help="gem5 resources download directory",
    )
    return parser


def run(benchmark: str, argv: list[str] | None = None) -> None:
    parser = build_parser(default_benchmark=benchmark)
    args = parser.parse_args(argv)
    args.benchmark = benchmark

    project_root = Path(args.project_root)
    results_dir = project_root / "results"
    disk_image = _resolve_path(args.disk_image)

    if not os.path.exists(disk_image):
        fatal_msg = (
            f"Disk image not found: {disk_image}\n"
            "Build it with: ./scripts/prepare_fs_disk_image.sh"
        )
        raise FileNotFoundError(fatal_msg)

    intervals, weights = load_simpoints(args.benchmark, results_dir)

    simpoint = SimpointResource(
        simpoint_interval=SIMPOINT_INTERVAL,
        simpoint_list=intervals,
        weight_list=weights,
        warmup_interval=args.warmup_interval,
    )
    simpoint_start_insts = list(simpoint.get_simpoint_start_insts())

    cache_hierarchy = PrivateL1PrivateL2CacheHierarchy(
        l1d_size="32KiB",
        l1i_size="32KiB",
        l2_size="256KiB",
    )
    memory = DualChannelDDR4_2400(size=FS_GUEST_MEMORY_SIZE)

    processor = SimpleProcessor(
        cpu_type=CPUTypes.KVM,
        isa=ISA.ARM,
        num_cores=args.num_cores,
    )
    kvm_cpu = processor.get_cores()[0].get_simobject()

    board = ArmBoard(
        clk_freq="3GHz",
        processor=processor,
        memory=memory,
        cache_hierarchy=cache_hierarchy,
        release=ArmDefaultRelease.for_kvm(),
        platform=VExpress_GEM5_V1(),
    )

    resource_kwargs = {}
    if args.resource_directory:
        resource_kwargs["resource_directory"] = args.resource_directory

    checkpoint = None
    if args.boot_checkpoint:
        boot_cpt = Path(_resolve_path(args.boot_checkpoint))
        if not boot_cpt.exists():
            raise FileNotFoundError(f"Boot checkpoint not found: {boot_cpt}")
        checkpoint = CheckpointResource(local_path=str(boot_cpt))

    readfile_contents = build_readfile_contents(
        args.benchmark,
        project_root,
        boot_checkpoint=bool(checkpoint),
    )

    partition = args.partition if args.partition != "" else None

    board.set_kernel_disk_workload(
        kernel=obtain_resource(
            "arm64-linux-kernel-6.8.12",
            resource_version="1.0.0",
            **resource_kwargs,
        ),
        disk_image=DiskImageResource(
            local_path=disk_image,
            root_partition=partition,
        ),
        bootloader=obtain_resource(
            "arm64-bootloader-foundation",
            resource_version="2.0.0",
            **resource_kwargs,
        ),
        readfile_contents=readfile_contents,
        checkpoint=checkpoint,
    )

    _ensure_kvm_perf(processor)
    attach_kvm_pmu(processor)

    checkpoint_dir = Path(_resolve_path(args.checkpoint_path))
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    register_continue_after_readfile_bridge()
    ensure_exit_on_work_items_after_checkpoint_restore(board)

    use_boot_checkpoint = bool(checkpoint)
    exit_handlers = {
        ExitEvent.EXIT: fs_exit_end_handler(
            kvm_cpu,
            use_boot_checkpoint,
            simpoint_start_insts,
        ),
        ExitEvent.SIMPOINT_BEGIN: fs_simpoint_checkpoint_generator(
            checkpoint_dir,
            intervals,
            weights,
            simpoint_start_insts,
            simpoint_interval=SIMPOINT_INTERVAL,
            warmup_interval=args.warmup_interval,
        ),
    }
    if not use_boot_checkpoint:
        exit_handlers[ExitEvent.WORKBEGIN] = fs_workbegin_handler(
            kvm_cpu, simpoint_start_insts
        )

    simulator = Simulator(
        board=board,
        on_exit_event=exit_handlers,
    )

    print(f"Benchmark:        {args.benchmark}")
    print(f"Disk image:       {disk_image}")
    print(f"CPU mode:         KVM (perf SimPoints)")
    print(f"SimPoints:        {len(intervals)}")
    print(f"Warmup interval:  {args.warmup_interval:,}")
    print(f"Checkpoint path:  {checkpoint_dir}")
    if checkpoint:
        print(f"Boot checkpoint:  {args.boot_checkpoint}")

    m5.stats.reset()
    simulator.run()

    print(
        "Exiting @ tick {} because {}.".format(
            simulator.get_current_tick(),
            simulator.get_last_exit_event_cause(),
        )
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args.benchmark, sys.argv[1:])


if __name__ in {"__main__", "__m5_main__"}:
    main()
