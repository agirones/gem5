from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.no_cache import NoCache
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.processors.simple_switchable_processor import SimpleSwitchableProcessor
from gem5.components.processors.cpu_types import CPUTypes
from gem5.isas import ISA
from gem5.resources.resource import obtain_resource
from gem5.simulate.simulator import Simulator
from gem5.simulate.exit_event import ExitEvent
from gem5.resources.resource import BinaryResource
# Import m5 for options and stats access
import m5

# --- COMPONENT SETUP (No Changes) ---

processor = SimpleSwitchableProcessor(
    starting_core_type=CPUTypes.KVM,
    switch_core_type=CPUTypes.ATOMIC,
    isa=ISA.ARM,
    num_cores=1
)

memory = SingleChannelDDR3_1600(size="16GiB")

cache_hierarchy = NoCache()

board = SimpleBoard(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy
)

# --- WORKLOAD SETUP (No Changes) ---

# Note: The local_path must be accessible by gem5 when running.
binary_path = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/600.perlbench_s/run/run_base_refspeed_arm-build-64.0000/perlbench_s_base.arm-build-64"
benchmark_binary = BinaryResource(local_path=binary_path)

checkspam_pl_file = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/600.perlbench_s/run/run_base_refspeed_arm-build-64.0000/checkspam.pl"
lib_path = "/home/andreug/research/microbenchmarks/spec2017/cpu2017/benchspec/CPU/600.perlbench_s/run/run_base_refspeed_arm-build-64.0000/lib"
# Ensure all arguments are strings for consistency
benchmark_arguments = [f"-I{lib_path}", checkspam_pl_file, "2500", "5", "25", "11", "150", "1", "1", "1", "1"]

board.set_se_binary_workload(
    binary=benchmark_binary,
    arguments=benchmark_arguments,
)

simulator = Simulator(board=board)

# --- EXECUTION LOGIC (The Fix) ---

def find_active_core_simobject(proc, is_kvm):
    """Utility to find the underlying SimObject for the currently active core."""
    for core in proc.get_cores():
        # is_kvm_core() identifies the type of core object created by SimpleSwitchableProcessor
        if core.is_kvm_core() == is_kvm: 
            # .core attribute gives access to the m5.objects.BaseCPU (the SimObject)
            return core.core 
    return None

# --- PHASE 1: KVM Execution (Limit by MaxInsts) ---

KVM_CORE = find_active_core_simobject(processor, is_kvm=True)
if KVM_CORE:
    # Set the global instruction limit for the currently active CPU SimObject.
    # We must use set_param_value because scheduleInstStop is unavailable.
    # The 'maxinsts' parameter triggers the 'Exit' event when reached.
    KVM_CORE.max_insts_any_thread = 10000000
    print("Phase 1: KVM MaxInsts set to 10M. Running...")
else:
    print("Error: Could not find KVM core SimObject.")
    exit(1)

# Reset stats right before running to ensure instruction count is accurate
m5.stats.reset()
exit_event = simulator.run()

if exit_event.getCause() == "max insts":
    print("Instruction limit reached on KVM. Switching to Atomic...")
    
    # Dump stats to capture the exact instructions executed by KVM
    m5.stats.dump()
    
    # --- The Switch ---
    processor.switch()
    
    # --- PHASE 2: ATOMIC Execution (Limit by MaxInsts) ---
    
    # Reset KVM maxinsts and set Atomic's limit
    KVM_CORE.max_insts_any_thread = 0 # Disable limit on the old core

    ATOMIC_CORE = find_active_core_simobject(processor, is_kvm=False)
    if ATOMIC_CORE:
        # We need a new instruction limit for the second phase
        ATOMIC_CORE.max_insts_any_thread = 10000000
        print("Atomic MaxInsts set to 10M. Running Phase 2...")
    else:
        print("Error: Could not find Atomic core SimObject.")
        exit(1)
    
    # Reset stats again to measure only the Atomic phase's instructions
    m5_reset_stats(0, 0)
    simulator.run()
    
    print(f"Simulation Finished. Cause: {simulator.get_last_exit_event_cause()}")

elif exit_event.getCause() == "exiting with last instruction: 'syscall_ret'":
    # This means the workload finished before hitting the 10M limit
    print(f"Workload finished on KVM before reaching 10M instruction limit. Exiting.")
    m5_dump_stats() # Dump final stats
else:
    print(f"Simulation ended early due to unexpected event: {exit_event.getCause()}")
    exit(0)

# Final stats dump
m5_dump_stats()