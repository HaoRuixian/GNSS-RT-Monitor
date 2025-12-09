"""
store for GNSS-IR focused observations.

The store keeps only the data that matches a configurable elevation/azimuth
window and automatically drops old samples to control memory usage.
"""
from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional
import threading


@dataclass
class IrSample:
    """Single filtered observation used for GNSS-IR analysis."""
    tow: float
    sys: str
    prn: str
    azimuth: float
    elevation: float
    signal_id: str
    snr: float
    pseudorange: float
    phase: float


class GnssIrStore:
    """
    Keep a rolling window of filtered GNSS observations for IR/LSP analysis.

    Notes on memory:
    - `keep_seconds` controls how long data is retained.
    - Data is stored as small dataclasses inside a deque; at 1 Hz with tens of
      satellites this typically stays in the low tens of MB.
    """
    def __init__(self, keep_seconds: int = 900):
        self.keep_seconds = keep_seconds
        self._data: deque[IrSample] = deque()
        self._lock = threading.Lock()

    def _az_allowed(self, az: float, az_windows: Iterable[Iterable[float]]) -> bool:
        """Check if azimuth is inside any configured window."""
        if not az_windows:
            return True
        for start, end in az_windows:
            if start <= az <= end:
                return True
        return False

    def add_epoch(self, tow: float, satellites: Dict[str, object], cfg: dict, active_systems: set):
        """
        Filter and append observations from one epoch.

        Args:
            tow: time-of-week in seconds.
            satellites: mapping like {'G01': SatelliteState, ...}
            cfg: configuration dict with min/max elevation, azimuth ranges.
            active_systems: systems currently enabled
        """
        min_el = cfg.get("MIN_ELEVATION_DEG", 0)
        max_el = cfg.get("MAX_ELEVATION_DEG", 90)
        az_windows = cfg.get("AZ_WINDOWS_DEG", [])

        with self._lock:
            # Drop expired samples
            cutoff = tow - self.keep_seconds
            while self._data and self._data[0].tow < cutoff:
                self._data.popleft()

            for sat_key, sat in satellites.items():
                sys_id = getattr(sat, "sys_id", sat_key[0])
                if sys_id not in active_systems:
                    continue

                el = getattr(sat, "el", None) or getattr(sat, "elevation", 0.0) or 0.0
                az = getattr(sat, "az", None) or getattr(sat, "azimuth", 0.0) or 0.0

                if el < min_el or el > max_el:
                    continue
                if not self._az_allowed(az, az_windows):
                    continue

                for sig_id, sig in getattr(sat, "signals", {}).items():
                    if not sig:
                        continue
                    snr = getattr(sig, "snr", 0.0) or 0.0
                    if snr <= 0:
                        continue
                    pr = getattr(sig, "pseudorange", 0.0) or 0.0
                    ph = getattr(sig, "phase", 0.0) or 0.0

                    self._data.append(
                        IrSample(
                            tow=tow,
                            sys=sys_id,
                            prn=sat_key,
                            azimuth=az,
                            elevation=el,
                            signal_id=sig_id,
                            snr=snr,
                            pseudorange=pr,
                            phase=ph,
                        )
                    )

    def get_series(
        self,
        prn: Optional[str] = None,
        sys: Optional[str] = None,
        signal_id: Optional[str] = None,
    ) -> List[IrSample]:
        """
        Return filtered samples for downstream processing (e.g., Lomb–Scargle).
        """
        with self._lock:
            return [
                s
                for s in list(self._data)
                if (prn is None or s.prn == prn)
                and (sys is None or s.sys == sys)
                and (signal_id is None or s.signal_id == signal_id)
            ]

    def size(self) -> int:
        with self._lock:
            return len(self._data)

