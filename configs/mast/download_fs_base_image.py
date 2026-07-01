"""
Download the gem5 ARM Ubuntu base disk image (no simulation).

Requires GEM5_RESOURCE_JSON pointing at a local JSON catalog (Atlas API is
broken in gem5 24.1). Prefer scripts/download_fs_base_image.sh instead.

    export GEM5_RESOURCE_JSON=fs_disk_images/gem5-resources-local.json
    build/ARM/gem5.opt configs/mast/download_fs_base_image.py
"""

from gem5.resources.resource import obtain_resource

RESOURCE_ID = "arm-ubuntu-24.04-npb-img"
RESOURCE_VERSION = "4.0.0"

resource = obtain_resource(RESOURCE_ID, resource_version=RESOURCE_VERSION)
print(f"Downloaded {RESOURCE_ID} to: {resource.get_local_path()}")
