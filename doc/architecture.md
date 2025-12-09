# GNSS RT Monitor - Architecture (Quick Reference)

This document explains the current structure, naming, and data flow so you can navigate the code quickly.

## Runtime Pipeline
- **I/O Threads (`ui/workers.py` → `IOThread`)**  
  Connect to NTRIP, read RTCM, push raw messages into a per-stream `RingBuffer` (non-blocking, drops oldest when full).
- **Processing Threads (`ui/workers.py` → `DataProcessingThread`)**  
  Pull RTCM from the ring buffer, parse via `RTCMHandler`, emit `epoch_signal` with merged `EpochObservation`.
- **GUI Thread (`ui/main_window.py` → `GNSSMonitorWindow.process_gui_epoch`)**  
  Merge/refresh satellite snapshots, append history, push filtered samples into the GNSS-IR store, update widgets with throttling (default 300 ms).

## Structural Sketch
```
NTRIP streams
   │
   ▼
IOThread (per stream)
   │  raw RTCM
   ▼
RingBuffer (drop-oldest, non-blocking)
   │  RTCM messages
   ▼
DataProcessingThread (per stream)
   │  EpochObservation
   ▼
Qt signal -> GNSSMonitorWindow.process_gui_epoch
   ├─ merged_satellites (latest snapshot)
   ├─ sat_history (per-PRN deque, plots)
   └─ ir_store (GNSS-IR filtered window)
        └─ get_ir_series(...) -> analysis (e.g., LSP)

UI widgets (Dashboard/SNR tabs)
   ├─ skyplot
   ├─ multi-signal bar chart
   └─ tables (per system, hashed refresh)
```

## Data Structures
- **`core/data_models.py`**  
  `SignalData`, `SatelliteState`, `EpochObservation` to hold parsed observations.
- **`core/ring_buffer.py`**  
  Thread-safe deque with drop-oldest semantics; used between I/O and processing threads.
- **`core/data_store.py` (`GnssIrStore`)**  
  Rolling in-memory store for GNSS-IR/LSP: filters by elevation/azimuth/system, retains for `KEEP_SECONDS`, returns series for analysis.

## UI Layout (`ui/main_window.py`)
- Main tabs:  
  - `Dashboard`: skyplot, multi-signal bar chart, per-system tables.  
  - `SNR Display`: time/elevation/sin(E) plots per PRN.
- Table update: hashes PRN + (El/Az/SNR/Pseudorange/Phase) rows to avoid needless redraws while still reacting to data changes.
- History: `sat_history` keeps 500 points per PRN (plots); `cleanup_stale_satellites` prunes unseen sats after 5 s.

## Configuration (`config.py`)
- `TARGET_SYSTEMS`: active GNSS systems (filters everywhere).
- NTRIP connection presets (choose one block).
- `GNSS_IR`: masks and retention for GNSS-IR/LSP. Default (user-adjusted):  
  - `KEEP_SECONDS`: 900  
  - `MIN_ELEVATION_DEG`: 12.0  
  - `MAX_ELEVATION_DEG`: 25.0  
  - `AZ_WINDOWS_DEG`: [[165, 330]]

## GNSS-IR / LSP Usage
- Data entry point: `GNSSMonitorWindow.get_ir_series(prn=None, signal_id=None)` returns filtered samples (with tow/snr/phase/pseudorange/az/el).
- Typical workflow: call `get_ir_series`, extract `tow` + chosen observable, run Lomb–Scargle or custom spectral analysis.

## Key Files and Responsibilities
- `gui_main.py`: App entry, palette/font setup, launch `GNSSMonitorWindow`.
- `ui/main_window.py`: UI, throttled refresh, history, GNSS-IR store hookup, restart logic.
- `ui/workers.py`: I/O + processing thread classes and Qt signals.
- `core/rtcm_handler.py`: Parse RTCM (ephemeris + MSM), compute az/el using ephemeris cache.
- `core/data_store.py`: GNSS-IR rolling store with masks and retention.

## Performance Notes
- Throttled GUI refresh (`gui_update_interval=0.3s`) and hash check on tables to keep UI smooth.
- Ring buffers drop oldest on overflow to keep I/O unblocked.
- GNSS-IR store trims by time; adjust `KEEP_SECONDS` to balance memory vs. window length.

