import os

class Benchmark:

    def __init__(self, name, num_runs, binary, args):
        self.name = name
        self.num_runs = num_runs
        self.binary = binary
        self.args = args


ALL_BENCHMARKS = []

script_dir = os.path.dirname(__file__)
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