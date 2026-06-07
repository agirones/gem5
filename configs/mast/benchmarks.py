import os

class Benchmark:

    def __init__(self, name, num_runs, binary, args, kind="spec"):
        self.name = name
        self.num_runs = num_runs
        self.binary = binary
        self.args = args
        # "spec"   -> static SPEC17 binary in /home/gem5/x86-static-17/<name>
        # "pyperf" -> pyperformance benchmark run from /home/gem5/pyperf
        self.kind = kind


ALL_BENCHMARKS = []

script_dir = os.path.dirname(__file__)

# Select which benchmark suite to expose via ALL_BENCHMARKS. Defaults to the
# legacy SPEC17 suite so existing runs are unchanged. Set GEM5_BENCH_SET=pyperf
# to expose the pyperformance benchmarks (requires the python disk image).
bench_set = os.getenv("GEM5_BENCH_SET", "spec")

if bench_set == "pyperf":
    with open(f"{script_dir}/pyperf-benchmarks.txt", "r") as pyperf_file:
        for line in pyperf_file:
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            ALL_BENCHMARKS.append(
                Benchmark(
                    name=name,
                    num_runs=1,
                    binary="python3",
                    args=[[]],
                    kind="pyperf",
                )
            )
else:
    with open(f"{script_dir}/spec17-benchmarks.txt", "r") as spec17:
        bmarks = {}
        for line in spec17:
            name = line.split()[0]
            if name in bmarks:
                bmarks[name].append(line)
            else:
                bmarks[name] = [line]

        for key, value in bmarks.items():
            bmark = Benchmark(
                name=key,
                num_runs=len(value),
                binary=value[0].split()[1][2:],
                args=[x.split()[2:] for x in value]
            )
            ALL_BENCHMARKS.append(bmark)
