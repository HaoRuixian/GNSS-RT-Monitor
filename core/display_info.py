
def print_epoch_header(epoch_data):
    print("=" * 68)
    print(f" EPOCH TIME : {epoch_data.gps_time}")
    print(f" NUM SATS   : {len(epoch_data.satellites)}")
    print("-" * 68)


def group_satellites_by_system(epoch_data):
    sys_map = {
        'G': 'GPS',
        'R': 'GLONASS',
        'E': 'Galileo',
        'C': 'BeiDou',
        'J': 'QZSS',
        'I': 'IRNSS',
        'S': 'SBAS'
    }

    sats_by_sys = {}
    for key, sat in epoch_data.satellites.items():
        sys_char = key[0]
        sats_by_sys.setdefault(sys_char, []).append((key, sat))

    return sats_by_sys, sys_map


def print_satellite_block(sys_char, sat_list, sys_map):
    print(f"\n [{sys_map.get(sys_char, 'UNKNOWN')}] ({len(sat_list)} sats)\n")
    print("  PRN   Signal  |  El(°)  Az(°)  |   SNR(dB)   Pseudorange(m)     CarrierPhase(cyc)")
    print(" ---------------------------------------------------------------------------------------")

    valid_count = 0

    for key, sat in sat_list:
        el_val = getattr(sat, "el", getattr(sat, "elevation", None))
        az_val = getattr(sat, "az", getattr(sat, "azimuth", None))

        el_str = f"{el_val:5.1f}" if el_val is not None else "  N/A"
        az_str = f"{az_val:5.1f}" if az_val is not None else "  N/A"

        for sig_code, sig in sat.signals.items():
            if sig is None:
                continue

            valid_count += 1
            snr = f"{sig.snr:5.1f}" if getattr(sig, "snr", None) else "  N/A"
            pr  = f"{sig.pseudorange:14.3f}" if getattr(sig, "pseudorange", None) else "      N/A"
            cp  = f"{sig.phase:16.3f}"       if getattr(sig, "phase", None)       else "        N/A"

            print(f"  {key:4}   {sig_code:4}   |  {el_str}  {az_str}  |   {snr}     {pr}     {cp}")

    return valid_count


def print_epoch_footer(epoch_data, valid_count):
    print(
        "\n--- EPOCH PROCESSED: "
        f"{epoch_data.gps_time} | Valid SNR sats = {valid_count} ---"
    )
    print("=" * 87 + "\n")
