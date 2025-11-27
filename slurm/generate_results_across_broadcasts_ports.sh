module load SciPy-bundle/2024.05-gfbf-2024a
module load matplotlib/3.9.2-gfbf-2024a

for W in {8..1}; do
    python3 ../runs/scripts/wakeup_data.py --base-dir "../runs/output/wakeupstats/baseline_fast_cache_no_dest_no_wake_up/${W}B/"
done