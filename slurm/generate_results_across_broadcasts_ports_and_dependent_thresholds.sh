module load SciPy-bundle/2024.05-gfbf-2024a
module load matplotlib/3.9.2-gfbf-2024a

for B in {1..5}; do
    for P in $(seq -1 -1); do
        python3 runs/scripts/wakeup_data.py --base-dir "runs/output/isca26/${B}B_${P}P/"
    done
done