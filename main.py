#!/usr/bin/env python3
import sys
import time
import threading
from pyrtcm import RTCMReader

import config
from core.ntrip_client import NtripClient
from core.rtcm_handler import RTCMHandler
from core.process import process_epoch


def stream_thread(name, client, handler):
    while True:
        sock = client.connect()
        if not sock:
            print(f"[{name}] Failed to connect. Retry in 3s...")
            time.sleep(3)
            continue

        try:
            reader = RTCMReader(sock)
            print(f"[{name}] Connected. Start streaming...")

            for raw, msg in reader:
                if msg is None:
                    continue

                epoch_data = handler.process_message(msg)
                if epoch_data:
                    process_epoch(epoch_data)

        except Exception as e:
            print(f"[{name}] Stream error: {e}")

        finally:
            client.close()
            time.sleep(2)


def main():
    # Caster：MSM 
    client_obs = NtripClient(
        config.NTRIP_HOST,
        config.NTRIP_PORT,
        config.MOUNTPOINT,
        config.USER,
        config.PASSWORD
    )

    handler = RTCMHandler()
    t_obs = threading.Thread(
        target=stream_thread,
        args=("OBS", client_obs, handler),
        daemon=True
    )
    t_obs.start()

    print("[Main] OBS stream started.")

    # Caster - BRDC
    eph_enabled = (
        hasattr(config, "EPH_HOST")
        and config.EPH_HOST not in (None, "", "0")
    )

    if eph_enabled:
        client_eph = NtripClient(
            config.EPH_HOST,
            config.EPH_PORT,
            config.EPH_MOUNTPOINT,
            config.EPH_USER,
            config.EPH_PASSWORD
        )

        t_eph = threading.Thread(
            target=stream_thread,
            args=("EPH", client_eph, handler),
            daemon=True
        )
        t_eph.start()

        print("[Main] EPH stream enabled and started.")
    else:
        print("[Main] EPH stream disabled (no config provided).")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Main] Stopped by user.")



if __name__ == "__main__":
    main()
