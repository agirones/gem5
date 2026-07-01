"""
Take a post-boot checkpoint on an ARM Ubuntu + SPEC disk image.

Run once per disk image / core count, then pass the checkpoint directory to
fs_take_checkpoints.py via --boot-checkpoint to skip KVM OS boot on later runs.

Uses the classic ExitEvent generator API (compatible with gem5 builds that do
not embed gem5.simulate.exit_handler).

Example:
    build/ARM/gem5.opt configs/mast/fs_take_boot_checkpoint.py \\
        --disk-image fs_disk_images/arm-ubuntu-spec2017-fpspeed.img \\
        --checkpoint-path fs_disk_images/boot-checkpoints/1core
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Generator, Optional

import m5
from m5.objects import (
    ArmDefaultRelease,
    VExpress_GEM5_V1,
)

from gem5.components.boards.arm_board import ArmBoard
from gem5.components.cachehierarchies.classic.private_l1_private_l2_cache_hierarchy import (
    PrivateL1PrivateL2CacheHierarchy,
)
from gem5.components.memory import DualChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import (
    DiskImageResource,
    obtain_resource,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.exit_event_generators import exit_generator
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires

from fs_spec_common import (
    BOOT_CHECKPOINT_READFILE,
    FS_GUEST_MEMORY_SIZE,
    attach_kvm_pmu,
    project_root_from_config,
)

requires(isa_required=ISA.ARM, kvm_required=True)


def save_boot_checkpoint_generator(
    checkpoint_dir: Path,
) -> Generator[Optional[bool], None, None]:
    while True:
        print(f"Taking post-boot checkpoint at {checkpoint_dir}")
        m5.checkpoint(checkpoint_dir.as_posix())
        yield False


def main() -> None:
    project_root = project_root_from_config()
    default_disk = project_root / "fs_disk_images/arm-ubuntu-spec2017-fpspeed.img"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--disk-image",
        type=str,
        default=str(default_disk),
        help="Full path to the ARM Ubuntu disk image",
    )
    parser.add_argument(
        "--partition",
        type=str,
        default="2",
        help="Root partition on the disk image",
    )
    parser.add_argument(
        "--checkpoint-path",
        type=str,
        required=True,
        help="Directory where the boot checkpoint will be saved",
    )
    parser.add_argument(
        "--num-cores",
        type=int,
        default=1,
        help="Number of CPU cores",
    )
    parser.add_argument(
        "--resource-directory",
        type=str,
        default=None,
        help="gem5 resources download directory",
    )
    args = parser.parse_args()

    disk_image = args.disk_image
    if disk_image[0] != "/":
        disk_image = os.path.abspath(disk_image)
    if not os.path.exists(disk_image):
        raise FileNotFoundError(
            f"Disk image not found: {disk_image}\n"
            "Build it with: ./scripts/prepare_fs_disk_image.sh"
        )

    checkpoint_path = Path(args.checkpoint_path)
    if not checkpoint_path.is_absolute():
        checkpoint_path = checkpoint_path.resolve()
    checkpoint_path.mkdir(parents=True, exist_ok=True)

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
    attach_kvm_pmu(processor)

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
        readfile_contents=BOOT_CHECKPOINT_READFILE,
        exit_on_work_items=True,
    )

    board.exit_on_work_items = True

    simulator = Simulator(
        board=board,
        on_exit_event={
            ExitEvent.CHECKPOINT: save_boot_checkpoint_generator(checkpoint_path),
            ExitEvent.EXIT: exit_generator(),
        },
    )

    print(f"Disk image:       {disk_image}")
    print(f"Checkpoint path:  {checkpoint_path}")
    print(f"CPU cores:        {args.num_cores}")

    simulator.run()

    print(
        "Exiting @ tick {} because {}.".format(
            simulator.get_current_tick(),
            simulator.get_last_exit_event_cause(),
        )
    )


if __name__ in {"__main__", "__m5_main__"}:
    main()
