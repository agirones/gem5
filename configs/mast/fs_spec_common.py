"""Shared helpers for ARM full-system SPEC CPU2017 fpspeed checkpoint configs."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Generator, Optional

import m5

SIMPOINT_INTERVAL = 10_000_000
DEFAULT_WARMUP_INTERVAL = 50_000_000
# Match SE simpoint configs (take_checkpoints/*-cpt-arm.py). 4GiB OOMs on 657.xz_s
# (~7GiB malloc) and 631.deepsjeng_s; re-take boot checkpoint after changing this.
FS_GUEST_MEMORY_SIZE = "16GiB"
GUEST_SPEC_ROOT = "/home/gem5/spec2017"
GUEST_SPEC_CPU = f"{GUEST_SPEC_ROOT}/benchspec/CPU"
GUEST_BBV_TMP = "/tmp/perf_bbv.out"
GUEST_BBV_LOG = "/tmp/perf_bbv.log"
GUEST_PERF_BBV = "/home/gem5/bin/perf_bbv"
STDIN_BENCHMARKS = {"603.bwaves_s", "654.roms_s"}

# Post-sync readfile bisect stages (fs_take_bbv.py --readfile-stage).
BBV_READFILE_STAGES = (
    "shell",
    "binary",
    "perf_diag",
    "perf_nosudo",
    "perf_sudo",
    "full",
)

# Guest readfile for fs_take_boot_checkpoint.py (hack_back_ckpt.rcS pattern).
# After ``m5 checkpoint``, restore resumes at ``m5 readfile`` and execs the
# per-run workload script from System.readfile (BBV/checkpoint readfile).
BOOT_CHECKPOINT_READFILE = """\
if [ -z "${GEM5_POST_CPT+x}" ]; then
  export GEM5_POST_CPT=1;
  m5 checkpoint;
  m5 readfile > /tmp/runscript;
  chmod 755 /tmp/runscript;
  if [ -s /tmp/runscript ]; then exec /tmp/runscript; fi;
fi;
m5 exit;
"""


def project_root_from_config() -> Path:
    """Return microbenchmarks repo root (parent of gem5/)."""
    return Path(__file__).resolve().parents[3]


def ensure_exit_on_work_items_after_checkpoint_restore(board) -> None:
    """Re-enable m5 workbegin/workend exits after boot-checkpoint restore.

    ``System.exit_on_work_items`` defaults to False and is serialized into
    boot checkpoints. Without this, guest ``m5 workbegin`` does not exit to
    the simulator and BBV/checkpoint sync handlers never run.

    Note: this updates the Python param only. The C++ ``System::Params`` copy
    used by ``pseudo_inst::workbegin`` is restored from the checkpoint; retake
    the boot checkpoint with ``fs_take_boot_checkpoint.py`` (``exit_on_work_items=True``)
    after changing that script, or ``m5 workbegin`` will not trap to the simulator.
    """
    orig = board._post_instantiate

    def _post_instantiate() -> None:
        orig()
        board.exit_on_work_items = True

    board._post_instantiate = _post_instantiate


def attach_kvm_pmu(processor, *, ppi_number: int = 23) -> None:
    """Attach ArmPMU so guest Linux can open HW perf events (guest perf_bbv).

    Without this, gem5 FS configs leave ``isa.pmu = NULL``; the guest kernel
    then rejects ``PERF_COUNT_HW_INSTRUCTIONS`` with ENOENT and perf_bbv fails.
    Re-take the boot checkpoint after changing CPU/PMU layout.
    """
    from m5.objects import (
        ArmPMU,
        ArmPPI,
    )
    from m5.params import isNullPointer

    for core in processor.get_cores():
        cpu = core.get_simobject()
        for isa in cpu.isa:
            if not isNullPointer(isa.pmu):
                continue
            pmu = ArmPMU(interrupt=ArmPPI(num=ppi_number))
            # CPU_CYCLES (event 0x11) is mandatory in PMU::regProbeListeners.
            # Cache probes are omitted (None) and skipped at register time.
            pmu.addArchEvents(cpu=cpu)
            isa.pmu = pmu


def boot_aware_exit_end_handler(
    kvm_cpu,
    *,
    boot_checkpoint_used: bool,
    on_post_sync=None,
    end_message: str = "End-of-benchmark m5 exit: stopping simulation",
) -> Generator[Optional[bool], None, None]:
    """Handle ``m5 exit`` for boot-checkpoint workload runs.

    ``BOOT_CHECKPOINT_READFILE`` saves at ``m5 checkpoint`` and resumes at
    ``m5 readfile`` + ``exec /tmp/runscript``. The workload script (built by
    ``build_*_readfile_contents``) must start with ``m5 exit;`` so the host
    can sync KVM instruction counting before the benchmark runs.
    """
    sync_pending = boot_checkpoint_used
    while True:
        insts = kvm_cpu.totalInsts()
        if sync_pending:
            sync_pending = False
            print(f"Post-sync m5 exit: KVM inst offset {insts:,}")
            if on_post_sync is not None:
                on_post_sync(kvm_cpu, insts)
            else:
                m5.stats.reset()
            yield False
            continue
        print(f"{end_message} (totalInsts={insts:,})")
        yield True


def boot_checkpoint_readfile_prefix() -> list[str]:
    """Leading ``m5 exit`` required for workload readfile after boot restore."""
    return ["m5 exit;"]


def register_continue_after_readfile_bridge() -> None:
    """Override gem5 25.1 hypercall 3 so readfile workloads keep running in the shell.

    After the readfile script finishes (final ``m5 exit``), gem5-bridge reports
    "Done running script" and issues hypercall 3. The default handler ends the
    simulation. Use ``m5 workbegin`` (not a mid-script ``m5 exit``) for the KVM
    inst sync so gem5-bridge runs the full workload before hypercall 3.
    """
    from gem5.simulate.exit_handler import ExitHandler
    from gem5.utils.override import overrides

    class _ContinueAfterReadfileBridge(ExitHandler, hypercall_num=3):
        @overrides(ExitHandler)
        def _process(self, simulator) -> None:
            pass

        @overrides(ExitHandler)
        def _exit_simulation(self) -> bool:
            return False


def find_run_dir_name(benchmark: str, spec_cpu: Path) -> str:
    run_root = spec_cpu / benchmark / "run"
    runs = sorted(run_root.glob("run_base_refspeed_*.0000"))
    if not runs:
        raise FileNotFoundError(f"No refspeed run directory for {benchmark}")
    return runs[0].name


def find_binary_name(run_dir: Path) -> str:
    candidates = sorted(run_dir.glob("*_base.arm-build-64"))
    if not candidates:
        raise FileNotFoundError(f"No *_base.arm-build-64 binary in {run_dir}")
    return candidates[0].name


def parse_valgrind_command(
    benchmark: str, valgrind_jobs_dir: Path
) -> tuple[list[str], str | None, str | None]:
    """Return (args, stdin_file, binary_basename) from a BBV job file."""
    job_file = valgrind_jobs_dir / f"{benchmark}.bbv.slurm"
    if not job_file.exists():
        raise FileNotFoundError(f"Missing BBV job: {job_file}")

    for line in job_file.read_text().splitlines():
        if "exp-bbv" not in line or "valgrind" not in line:
            continue
        match = re.search(r"bb-out-file=\$OUTPUT_PATH\s+(.+)$", line)
        if not match:
            continue
        full = match.group(1).strip()
        stdin_file = None
        if "<" in full:
            cmd_part, stdin_file = full.split("<", 1)
            stdin_file = stdin_file.strip()
            full = cmd_part.strip()
        parts = shlex.split(full)
        if len(parts) < 1:
            raise ValueError(f"Empty valgrind command in {job_file}")
        binary_basename = Path(parts[0]).name
        return parts[1:], stdin_file, binary_basename

    raise ValueError(f"Could not parse valgrind command from {job_file}")


def parse_valgrind_args(benchmark: str, valgrind_jobs_dir: Path) -> list[str]:
    args, _stdin, _binary = parse_valgrind_command(benchmark, valgrind_jobs_dir)
    return args


def resolve_guest_arguments(args: list[str], guest_run_dir: str) -> list[str]:
    resolved: list[str] = []
    for arg in args:
        if arg.startswith("-I"):
            inc = arg[2:]
            if inc.startswith("./"):
                inc = inc[2:]
            resolved.append(f"-I{guest_run_dir}/{inc}")
            continue

        if arg.startswith("./"):
            resolved.append(f"{guest_run_dir}/{arg[2:]}")
            continue

        resolved.append(arg)
    return resolved


def load_simpoints(
    benchmark: str, results_dir: Path
) -> tuple[list[int], list[float]]:
    simpts_file = results_dir / benchmark / f"{benchmark}.bb.out.simpts"
    weights_file = results_dir / benchmark / f"{benchmark}.bb.out.weights"

    intervals = [
        int(line.split()[0])
        for line in simpts_file.read_text().splitlines()
        if line.strip()
    ]
    weights = [
        float(line.split()[0])
        for line in weights_file.read_text().splitlines()
        if line.strip()
    ]

    if len(intervals) != len(weights):
        raise ValueError(
            f"{benchmark}: {len(intervals)} simpoints vs {len(weights)} weights"
        )
    return intervals, weights


def legacy_simpoint_warmup_start(
    interval_id: int,
    simpoint_interval: int,
    warmup_interval: int,
) -> tuple[int, int]:
    """Return (starting_inst_count, warmup_length) for legacy checkpoint dir names.

    Matches profile-config-legacy.py parseSimpoints() used by invoke-run.py.
    """
    roi_start = interval_id * simpoint_interval
    if roi_start - warmup_interval > 0:
        return roi_start - warmup_interval, warmup_interval
    return 0, roi_start


def simpoint_checkpoint_dir_name(
    simpoint_index: int,
    interval_id: int,
    weight: float,
    simpoint_interval: int,
    warmup_interval: int,
) -> str:
    """Directory name for one SimPoint checkpoint (legacy invoke-run layout)."""
    starting_inst_count, warmup_length = legacy_simpoint_warmup_start(
        interval_id, simpoint_interval, warmup_interval
    )
    return (
        f"cpt.simpoint_{simpoint_index}_inst_{starting_inst_count}_weight_{weight}"
        f"_interval_{simpoint_interval}_warmup_{warmup_length}"
    )


def simpoints_in_fire_order(
    interval_ids: list[int],
    weights: list[float],
    warmup_start_insts: list[int],
) -> list[tuple[int, int, float, int]]:
    """Return (start_inst, interval_id, weight, simpoint_index) in fire order."""
    if not (len(interval_ids) == len(weights) == len(warmup_start_insts)):
        raise ValueError("SimPoint lists length mismatch")
    indexed = list(enumerate(zip(interval_ids, weights, warmup_start_insts)))
    return sorted(
        ((start, interval_id, weight, sp_idx) for sp_idx, (interval_id, weight, start) in indexed),
        key=lambda item: item[0],
    )


def fs_simpoint_checkpoint_generator(
    checkpoint_dir: Path,
    interval_ids: list[int],
    weights: list[float],
    warmup_start_insts: list[int],
    *,
    simpoint_interval: int = SIMPOINT_INTERVAL,
    warmup_interval: int = DEFAULT_WARMUP_INTERVAL,
) -> Generator[Optional[bool], None, None]:
    """Save SimPoint checkpoints using legacy cpt.simpoint_* directory names."""
    import m5

    entries = simpoints_in_fire_order(interval_ids, weights, warmup_start_insts)
    total = len(entries)
    count = 0
    n_done = 0
    last_start = -1

    while True:
        start_inst, sp_id, weight, sp_index = entries[count]
        dir_name = simpoint_checkpoint_dir_name(
            sp_index, sp_id, weight, simpoint_interval, warmup_interval
        )
        n_done += 1
        print(
            f"SimPoint checkpoint [{n_done}/{total}]: interval={sp_id} "
            f"weight={weight:g} @ inst {start_inst:,} -> {dir_name}/"
        )
        m5.checkpoint((checkpoint_dir / dir_name).as_posix())
        last_start = start_inst
        count += 1
        while count < len(entries) and last_start == entries[count][0]:
            start_inst, sp_id, weight, sp_index = entries[count]
            dir_name = simpoint_checkpoint_dir_name(
                sp_index, sp_id, weight, simpoint_interval, warmup_interval
            )
            n_done += 1
            print(
                f"SimPoint checkpoint (shared inst) [{n_done}/{total}]: "
                f"interval={sp_id} weight={weight:g} -> {dir_name}/"
            )
            m5.checkpoint((checkpoint_dir / dir_name).as_posix())
            last_start = start_inst
            count += 1
        if count < len(entries):
            yield False
        else:
            print(
                f"All {len(entries)} SimPoint checkpoints taken; stopping simulation"
            )
            yield True


def guest_run_dir(benchmark: str, spec_cpu: Path) -> str:
    run_name = find_run_dir_name(benchmark, spec_cpu)
    return f"{GUEST_SPEC_CPU}/{benchmark}/run/{run_name}"


def bbv_jobs_dir(project_root: Path) -> Path:
    """Workload source of truth: bbv_jobs/ with legacy valgrind_jobs/ fallback."""
    preferred = project_root / "job_submissions/bbv_jobs"
    if preferred.exists():
        return preferred
    return project_root / "job_submissions/valgrind_jobs"


def build_readfile_contents(
    benchmark: str,
    project_root: Path,
    spec_cpu: Path | None = None,
    valgrind_jobs_dir: Path | None = None,
    boot_checkpoint: bool = False,
) -> str:
    if spec_cpu is None:
        spec_cpu = project_root / "spec2017/cpu2017/benchspec/CPU"
    if valgrind_jobs_dir is None:
        valgrind_jobs_dir = bbv_jobs_dir(project_root)

    run_dir_host = spec_cpu / benchmark / "run" / find_run_dir_name(
        benchmark, spec_cpu
    )
    raw_args, stdin_file, binary_name = parse_valgrind_command(
        benchmark, valgrind_jobs_dir
    )
    if binary_name is None:
        binary_name = find_binary_name(run_dir_host)
    guest_dir = guest_run_dir(benchmark, spec_cpu)
    args = resolve_guest_arguments(raw_args, guest_dir)

    # With boot checkpoint restore, leading m5 exit re-attaches gem5-bridge to
    # the workload readfile (603 checkpoint pattern). Cold boot uses m5
    # workbegin after cd so gem5-bridge is not cut off mid-script on 25.1.
    lines: list[str] = []
    if boot_checkpoint:
        lines.extend(boot_checkpoint_readfile_prefix())
    lines.append(f"cd {guest_dir} || exit 1;")
    if not boot_checkpoint:
        lines.append("m5 workbegin;")

    if benchmark in STDIN_BENCHMARKS:
        if stdin_file is None:
            raise ValueError(f"{benchmark}: missing stdin file in valgrind job")
        stdin_path = (
            f"{guest_dir}/{stdin_file}"
            if not stdin_file.startswith("/")
            else stdin_file
        )
        quoted_args = " ".join(shlex.quote(arg) for arg in args)
        lines.append(
            f"echo benchmark-start; "
            f"./{binary_name} {quoted_args} < {stdin_path}; "
            f"echo benchmark-end exit=$?;"
        )
    else:
        quoted = " ".join(shlex.quote(arg) for arg in args)
        lines.append(
            f"echo benchmark-start; ./{binary_name} {quoted}; "
            f"echo benchmark-end exit=$?;"
        )

    lines.append("m5 exit;")
    return "\n".join(lines)


def _bbv_workload_lines(
    benchmark: str,
    guest_dir: str,
    binary_name: str,
    binary_path: str,
    args: list[str],
    stdin_file: str | None,
    *,
    use_sudo: bool,
    log_to_file: bool,
) -> list[str]:
    """Run perf_bbv after sync m5 workbegin (optional sudo; optional log redirect)."""
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    perf = GUEST_PERF_BBV if not use_sudo else f"sudo -n {GUEST_PERF_BBV}"
    bbv_cmd = (
        f"{perf} -o {GUEST_BBV_TMP} "
        f"--interval {SIMPOINT_INTERVAL} -- {shlex.quote(binary_path)} "
        f"{quoted_args}"
    )
    if log_to_file:
        bbv_run = (
            f"{{ echo benchmark-start; echo paranoid="
            f"$(cat /proc/sys/kernel/perf_event_paranoid); "
            f"{bbv_cmd}; bbv_rc=$?; echo benchmark-end exit=$bbv_rc; "
            f"}} > {GUEST_BBV_LOG} 2>&1; cat {GUEST_BBV_LOG};"
        )
    else:
        bbv_run = (
            f"echo benchmark-start; echo paranoid="
            f"$(cat /proc/sys/kernel/perf_event_paranoid); "
            f"{bbv_cmd}; echo benchmark-end exit=$?;"
        )

    if benchmark in STDIN_BENCHMARKS:
        if stdin_file is None:
            raise ValueError(f"{benchmark}: missing stdin file in BBV job")
        stdin_path = (
            f"{guest_dir}/{stdin_file}"
            if not stdin_file.startswith("/")
            else stdin_file
        )
        return [f"{bbv_run} < {stdin_path}"]
    return [bbv_run]


def _perf_diag_readfile_lines() -> list[str]:
    """Guest PMU / perf_bbv diagnostics (bisect stage perf_diag)."""
    return [
        "echo perf_diag-start;",
        "echo paranoid=$(cat /proc/sys/kernel/perf_event_paranoid);",
        f"echo perf_bbv_path={GUEST_PERF_BBV};",
        f"ls -la {GUEST_PERF_BBV} /usr/local/bin/perf_bbv 2>&1 || true;",
        "echo '--- mount (/, /usr) ---';",
        "mount | grep -E ' on / | on /usr' || true;",
        "echo '--- /sys/bus/event_source/devices ---';",
        "ls -la /sys/bus/event_source/devices/ 2>&1 "
        "|| echo MISSING /sys/bus/event_source/devices;",
        "for d in /sys/bus/event_source/devices/*; do "
        '[ -e "$d" ] || continue; '
        'echo "  $(basename "$d") type=$(cat "$d/type" 2>/dev/null) '
        'cpumask=$(cat "$d/cpumask" 2>/dev/null)"; '
        "done;",
        "echo '--- /proc/device-tree (pmu compatible) ---';",
        "find /proc/device-tree -name compatible 2>/dev/null | while read f; do "
        "tr '\\0' '\\n' < \"$f\" | grep -qi pmu || continue; "
        "echo \"node $(dirname \"$f\" | sed 's|^/proc/device-tree/||'):\"; "
        "tr '\\0' ' ' < \"$f\"; echo; "
        "for p in reg interrupts interrupt-parent status; do "
        '[ -f "$(dirname "$f")/$p" ] || continue; '
        'echo "  $p=$(tr "\\0" " " < "$(dirname "$f")/$p" 2>/dev/null)"; '
        "done; "
        "done;",
        "echo '--- /proc/device-tree (armv8-pmuv3) ---';",
        "find /proc/device-tree -name compatible 2>/dev/null | while read f; do "
        "tr '\\0' '\\n' < \"$f\" | grep -q armv8-pmuv3 || continue; "
        "echo \"FOUND $(dirname \"$f\" | sed 's|^/proc/device-tree/||')\"; "
        "tr '\\0' ' ' < \"$f\"; echo; "
        "done;",
        "echo '--- dmesg pmu (tail) ---';",
        "dmesg 2>/dev/null | grep -i pmu | tail -20 || echo 'dmesg unavailable';",
        "if command -v perf >/dev/null 2>&1; then "
        "echo '--- perf list hw ---'; perf list hw 2>&1 | head -30; "
        "else echo 'perf(1) not in PATH'; fi;",
        "echo '--- perf_bbv probe (/bin/true) ---';",
        f"{GUEST_PERF_BBV} -o /tmp/perf_diag.out --interval 1000 -- /bin/true; "
        "echo perf_bbv_probe_exit=$?;",
        "echo perf_diag-end;",
        "m5 exit;",
    ]


def build_bbv_readfile_contents(
    benchmark: str,
    project_root: Path,
    guest_write_name: str,
    guest_log_name: str = "perf_bbv.guest.log",
    spec_cpu: Path | None = None,
    jobs_dir: Path | None = None,
    stage: str = "full",
    boot_checkpoint: bool = False,
) -> str:
    """Guest readfile: sync, perf_bbv workload, m5 writefile to gem5 outdir."""
    if stage not in BBV_READFILE_STAGES:
        raise ValueError(
            f"Unknown readfile stage {stage!r}; expected one of {BBV_READFILE_STAGES}"
        )
    if spec_cpu is None:
        spec_cpu = project_root / "spec2017/cpu2017/benchspec/CPU"
    if jobs_dir is None:
        jobs_dir = bbv_jobs_dir(project_root)

    run_dir_host = spec_cpu / benchmark / "run" / find_run_dir_name(
        benchmark, spec_cpu
    )
    raw_args, stdin_file, binary_name = parse_valgrind_command(benchmark, jobs_dir)
    if binary_name is None:
        binary_name = find_binary_name(run_dir_host)
    guest_dir = guest_run_dir(benchmark, spec_cpu)
    args = resolve_guest_arguments(raw_args, guest_dir)
    binary_path = f"{guest_dir}/{binary_name}"

    lines: list[str] = []
    if boot_checkpoint:
        lines.extend(boot_checkpoint_readfile_prefix())
    lines.append(f"cd {guest_dir} || exit 1;")
    if not boot_checkpoint:
        lines.append("m5 workbegin;")

    if stage == "shell":
        lines.extend(["echo bisect-shell-ok;", "m5 exit;"])
        return "\n".join(lines)

    if stage == "binary":
        if benchmark in STDIN_BENCHMARKS:
            if stdin_file is None:
                raise ValueError(f"{benchmark}: missing stdin file in BBV job")
            stdin_path = (
                f"{guest_dir}/{stdin_file}"
                if not stdin_file.startswith("/")
                else stdin_file
            )
            quoted_args = " ".join(shlex.quote(arg) for arg in args)
            lines.append(
                f"echo benchmark-start; ./{binary_name} {quoted_args} "
                f"< {stdin_path}; echo benchmark-end exit=$?;"
            )
        else:
            quoted = " ".join(shlex.quote(arg) for arg in args)
            lines.append(
                f"echo benchmark-start; ./{binary_name} {quoted}; "
                f"echo benchmark-end exit=$?;"
            )
        lines.append("m5 exit;")
        return "\n".join(lines)

    if stage == "perf_diag":
        lines.extend(_perf_diag_readfile_lines())
        return "\n".join(lines)

    lines.append(f"rm -f {GUEST_BBV_TMP} {GUEST_BBV_LOG};")

    if stage in {"perf_sudo", "full"}:
        lines.append(
            "sudo -n sysctl -w kernel.perf_event_paranoid=-1 >/dev/null 2>&1 || true;"
        )

    lines.extend(
        _bbv_workload_lines(
            benchmark,
            guest_dir,
            binary_name,
            binary_path,
            args,
            stdin_file,
            use_sudo=stage in {"perf_sudo", "full"},
            log_to_file=stage == "full",
        )
    )

    if stage == "full":
        host_bb_out = shlex.quote(guest_write_name)
        host_bb_log = shlex.quote(guest_log_name)
        lines.append(
            f"if test -s {GUEST_BBV_TMP}; then "
            f"m5 writefile {GUEST_BBV_TMP} {host_bb_out}; "
            f"else echo MISSING {GUEST_BBV_TMP} after perf_bbv; "
            f"cat {GUEST_BBV_LOG}; fi;"
        )

    lines.append("m5 exit;")
    return "\n".join(lines)


def build_host_bbv_readfile_contents(
    benchmark: str,
    project_root: Path,
    spec_cpu: Path | None = None,
    jobs_dir: Path | None = None,
    stage: str = "full",
    boot_checkpoint: bool = False,
) -> str:
    """Guest readfile: m5 workbegin sync, SPEC workload (host-side BBV)."""
    if stage not in {"shell", "binary", "full"}:
        raise ValueError(
            f"Unknown host BBV readfile stage {stage!r}; "
            "expected shell, binary, or full"
        )
    if spec_cpu is None:
        spec_cpu = project_root / "spec2017/cpu2017/benchspec/CPU"
    if jobs_dir is None:
        jobs_dir = bbv_jobs_dir(project_root)

    run_dir_host = spec_cpu / benchmark / "run" / find_run_dir_name(
        benchmark, spec_cpu
    )
    raw_args, stdin_file, binary_name = parse_valgrind_command(benchmark, jobs_dir)
    if binary_name is None:
        binary_name = find_binary_name(run_dir_host)
    guest_dir = guest_run_dir(benchmark, spec_cpu)
    args = resolve_guest_arguments(raw_args, guest_dir)
    binary_path = f"{guest_dir}/{binary_name}"

    lines: list[str] = []
    if boot_checkpoint:
        lines.extend(boot_checkpoint_readfile_prefix())
    lines.append(f"cd {guest_dir} || exit 1;")
    lines.append("m5 workbegin;")

    if stage == "shell":
        lines.extend(["echo bisect-shell-ok;", "m5 exit;"])
        return "\n".join(lines)

    if benchmark in STDIN_BENCHMARKS:
        if stdin_file is None:
            raise ValueError(f"{benchmark}: missing stdin file in BBV job")
        stdin_path = (
            f"{guest_dir}/{stdin_file}"
            if not stdin_file.startswith("/")
            else stdin_file
        )
        quoted_args = " ".join(shlex.quote(arg) for arg in args)
        lines.append(
            f"echo benchmark-start; {binary_path} {quoted_args} "
            f"< {stdin_path}; echo benchmark-end exit=$?;"
        )
    else:
        quoted = " ".join(shlex.quote(arg) for arg in args)
        lines.append(
            f"echo benchmark-start; {binary_path} {quoted}; "
            f"echo benchmark-end exit=$?;"
        )

    lines.append("m5 exit;")
    return "\n".join(lines)
