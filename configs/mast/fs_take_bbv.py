"""
ARM full-system host-side BBV collection with KVM fast-forward.

Boots the SPEC disk image, runs the benchmark in the guest, and collects
SimPoint G-format BBVs on the host via gem5 KVM perf IP sampling.

Example:
    build/ARM/gem5.opt configs/mast/fs_take_bbv.py \\
        --benchmark 998.specrand_is \\
        --bb-out-path results/998.specrand_is/998.specrand_is.bb.out
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
from gem5.components.boards.arm_board import ArmBoard
from gem5.components.cachehierarchies.classic.private_l1_private_l2_cache_hierarchy import (
    PrivateL1PrivateL2CacheHierarchy,
)
from gem5.components.memory import DualChannelDDR4_2400
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.isas import ISA
from gem5.resources.resource import (
    CheckpointResource,
    DiskImageResource,
    obtain_resource,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires

from fs_spec_common import (
    BBV_READFILE_STAGES,
    FS_GUEST_MEMORY_SIZE,
    SIMPOINT_INTERVAL,
    boot_aware_exit_end_handler,
    build_bbv_readfile_contents,
    build_host_bbv_readfile_contents,
    ensure_exit_on_work_items_after_checkpoint_restore,
    project_root_from_config,
    register_continue_after_readfile_bridge,
)

requires(isa_required=ISA.ARM, kvm_required=True)

HOST_BBV_STAGES = {"shell", "binary", "full"}


def fs_bbv_workbegin_handler(
    kvm_cpu: BaseCPU,
) -> Generator[Optional[bool], None, None]:
    """Benchmark-start sync: start host BBV collection at m5 workbegin."""
    while True:
        print(f"Post-sync m5 workbegin: KVM inst offset {kvm_cpu.totalInsts():,}")
        kvm_cpu.startBbvCollection()
        m5.stats.reset()
        yield False


def fs_bbv_exit_end_handler(
    kvm_cpu: BaseCPU,
    boot_checkpoint_used: bool,
) -> Generator[Optional[bool], None, None]:
    """Final m5 exit ends the BBV run."""
    if hasattr(kvm_cpu, "stopBbvCollection"):
        kvm_cpu.stopBbvCollection()
    yield from boot_aware_exit_end_handler(
        kvm_cpu,
        boot_checkpoint_used=boot_checkpoint_used,
    )


def _resolve_path(path: str) -> str:
    if path[0] != "/":
        return os.path.abspath(path)
    return path


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
        "--bb-out-path",
        type=str,
        default=None,
        help="Host path for the uncompressed BBV output file",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=str(project_root),
        help="Microbenchmarks repo root (for BBV job commands)",
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
    parser.add_argument(
        "--readfile-stage",
        type=str,
        choices=BBV_READFILE_STAGES,
        default="full",
        help=(
            "Readfile stage: shell, binary, full (host BBV); "
            "perf_diag, perf_nosudo, perf_sudo (legacy guest bisect)"
        ),
    )
    return parser


def run(benchmark: str, argv: list[str] | None = None) -> None:
    parser = build_parser(default_benchmark=benchmark)
    args = parser.parse_args(argv)
    args.benchmark = benchmark

    project_root = Path(args.project_root)
    disk_image = _resolve_path(args.disk_image)

    if not os.path.exists(disk_image):
        raise FileNotFoundError(
            f"Disk image not found: {disk_image}\n"
            "Build it with: ./scripts/prepare_fs_disk_image.sh"
        )

    if args.bb_out_path:
        bb_out_path = _resolve_path(args.bb_out_path)
    else:
        bb_out_path = str(project_root / "results" / benchmark / f"{benchmark}.bb.out")

    use_host_bbv = args.readfile_stage in HOST_BBV_STAGES

    Path(bb_out_path).parent.mkdir(parents=True, exist_ok=True)
    if use_host_bbv and Path(bb_out_path).exists():
        Path(bb_out_path).unlink()

    resource_kwargs = {}
    if args.resource_directory:
        resource_kwargs["resource_directory"] = args.resource_directory

    checkpoint = None
    if args.boot_checkpoint:
        boot_cpt = Path(_resolve_path(args.boot_checkpoint))
        if not boot_cpt.exists():
            raise FileNotFoundError(f"Boot checkpoint not found: {boot_cpt}")
        checkpoint = CheckpointResource(local_path=str(boot_cpt))

    if use_host_bbv:
        readfile_contents = build_host_bbv_readfile_contents(
            benchmark,
            project_root,
            stage=args.readfile_stage,
            boot_checkpoint=bool(checkpoint),
        )
    else:
        guest_write_name = f"{benchmark}.bb.out"
        readfile_contents = build_bbv_readfile_contents(
            benchmark,
            project_root,
            guest_write_name,
            stage=args.readfile_stage,
            boot_checkpoint=bool(checkpoint),
        )

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
    for core in processor.get_cores():
        cpu = core.get_simobject()
        if hasattr(cpu, "usePerf"):
            cpu.usePerf = True
        if hasattr(cpu, "perfExcludeKernel"):
            cpu.perfExcludeKernel = True
        if use_host_bbv and args.readfile_stage == "full":
            cpu.collectBbv = True
            cpu.bbvOutPath = bb_out_path
            cpu.bbvInterval = SIMPOINT_INTERVAL

    board = ArmBoard(
        clk_freq="3GHz",
        processor=processor,
        memory=memory,
        cache_hierarchy=cache_hierarchy,
        release=ArmDefaultRelease.for_kvm(),
        platform=VExpress_GEM5_V1(),
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

    register_continue_after_readfile_bridge()
    ensure_exit_on_work_items_after_checkpoint_restore(board)

    use_boot_checkpoint = bool(checkpoint)
    exit_handlers = {
        ExitEvent.EXIT: fs_bbv_exit_end_handler(kvm_cpu, use_boot_checkpoint),
    }
    if use_host_bbv and args.readfile_stage == "full":
        exit_handlers[ExitEvent.WORKBEGIN] = fs_bbv_workbegin_handler(kvm_cpu)

    simulator = Simulator(
        board=board,
        on_exit_event=exit_handlers,
    )

    mode = "KVM (host perf BBV)" if use_host_bbv else "KVM (legacy guest bisect)"
    print(f"Benchmark:        {args.benchmark}")
    print(f"Disk image:       {disk_image}")
    print(f"CPU mode:         {mode}")
    print(f"Readfile stage:   {args.readfile_stage}")
    if use_host_bbv and args.readfile_stage == "full":
        print(f"BBV output:       {bb_out_path}")
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

    outdir = Path(m5.options.outdir)

    if args.readfile_stage != "full":
        terminal = outdir / "board.terminal"
        print(f"Bisect stage {args.readfile_stage!r} finished (BBV output not required).")
        if terminal.exists():
            term_text = terminal.read_text(errors="replace")
            for marker in (
                "bisect-shell-ok",
                "perf_diag-start",
                "perf_diag-end",
                "perf_bbv_probe_exit",
                "benchmark-start",
                "benchmark-end",
                "I/O error",
                "virtio_blk",
            ):
                if marker in term_text:
                    print(f"  terminal contains: {marker!r}")
        return

    if use_host_bbv:
        if not Path(bb_out_path).exists():
            terminal = outdir / "board.terminal"
            hint = ""
            if terminal.exists():
                term_text = terminal.read_text(errors="replace").strip()
                if term_text:
                    hint = f"\nGuest terminal tail ({terminal}):\n{term_text[-4000:]}"
            raise FileNotFoundError(
                f"BBV file not written by host collector: {bb_out_path}\n"
                "Check that m5 workbegin fired and host perf IP sampling succeeded."
                f"{hint}"
            )
        return

    # Legacy guest perf_bbv path (bisect stages perf_* only reach here if full)
    guest_write_name = f"{benchmark}.bb.out"
    guest_log_name = "perf_bbv.guest.log"
    outdir_bb = outdir / guest_write_name
    outdir_log = outdir / guest_log_name
    final_log = Path(bb_out_path).parent / guest_log_name

    if outdir_bb.exists():
        outdir_bb.replace(bb_out_path)
    if outdir_log.exists():
        outdir_log.replace(final_log)

    if not Path(bb_out_path).exists():
        hint = ""
        if final_log.exists():
            hint = f"\nGuest log ({final_log}):\n{final_log.read_text()[-4000:]}"
        terminal = outdir / "board.terminal"
        if not hint and terminal.exists():
            term_text = terminal.read_text(errors="replace").strip()
            if term_text:
                hint = f"\nGuest terminal tail ({terminal}):\n{term_text[-4000:]}"
        raise FileNotFoundError(
            f"BBV file not written by guest: {bb_out_path}\n"
            "Check perf_bbv.guest.log for benchmark-end exit code and "
            "perf_event_open errors."
            f"{hint}"
        )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args.benchmark, sys.argv[1:])


if __name__ in {"__main__", "__m5_main__"}:
    main()
