module load SciPy-bundle/2024.05-gfbf-2024a
module load matplotlib/3.9.2-gfbf-2024a

PARENT_DIR="runs/output/isca26/iq_size"

for SUBDIR in ${PARENT_DIR}/*/; do
    if [ -d "$SUBDIR" ]; then
        python3 runs/scripts/wakeup_data.py --base-dir "$SUBDIR"
    fi
done