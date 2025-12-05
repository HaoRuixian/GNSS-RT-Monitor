"""
Data models for storing GNSS observations and satellite states.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class SignalData:
    """
    Holds observation data for a specific frequency/signal.
    """
    signal_id: str        # e.g., "1C", "2W"
    snr: float            # dB-Hz
    phase: float          # cycles
    pseudorange: float    # meters
    lock_time: int   
    half_cycle: int
    doppler: float

@dataclass
class SatelliteState:
    """
    Represents the state of a single satellite at a specific epoch.
    """
    sys_id: str           # 'G', 'E', 'C', 'R'
    prn: int              # Satellite ID
    
    # Geometric Data (Calculated from Ephemeris)
    azimuth: Optional[float] = None    # Degrees (0-360)
    elevation: Optional[float] = None  # Degrees (-90 to 90)
    sat_pos_ecef: Optional[list] = None # [x, y, z]
    
    # Signal Data: Key is signal_id (e.g., "1C")
    signals: Dict[str, SignalData] = field(default_factory=dict)

@dataclass
class EpochObservation:
    """
    Container for all data in a single time epoch.
    """
    gps_time: float       # GPS Time of Week (seconds)
    satellites: Dict[str, SatelliteState] = field(default_factory=dict)