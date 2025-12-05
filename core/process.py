# process_utils.py
from core.display_info import (
    print_epoch_header,
    group_satellites_by_system,
    print_satellite_block,
    print_epoch_footer,
)

def process_epoch(epoch_data):
    print_epoch_header(epoch_data)

    sats_by_sys, sys_map = group_satellites_by_system(epoch_data)

    total_valid = 0
    for sys_char, sat_list in sats_by_sys.items():
        total_valid += print_satellite_block(sys_char, sat_list, sys_map)

    print_epoch_footer(epoch_data, total_valid)
