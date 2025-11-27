module load SciPy-bundle/2024.05-gfbf-2024a
module load matplotlib/3.9.2-gfbf-2024a

for B in {4..12}; do
    for P in $(seq -1 0); do
        python3 ../runs/scripts/wakeup_data.py --base-dir "../runs/output/wakeupstats/japanese_fast_no_dest_no_wake_up/${B}B_${P}P/"
    done
done