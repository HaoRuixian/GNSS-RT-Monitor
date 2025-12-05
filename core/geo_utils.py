"""
Geometry utilities for GNSS coordinate transformations and orbit calculations.
"""
import numpy as np
import math

# WGS84 Constants
CLIGHT = 299792458.0       # Speed of light

def get_freq(sig_id: str, sat_key: str, fcn: int = 0):
    """
    Get frequency and wavelength based on Signal ID and Satellite Key.
    
    Args:
        sig_id: Signal ID (e.g., "1C", "2W")
        sat_key: Satellite Key (e.g., "G14", "R01")
        fcn: Frequency Channel Number (Required for GLONASS, -7 to +6)
    
    Returns:
        (frequency_Hz, wavelength_m)
    """
    # 1. Define base frequencies
    # GPS / QZSS
    gps_freq = {"1": 1575.42e6, "2": 1227.60e6, "5": 1176.45e6, "6": 1278.75e6}
    # Galileo
    gal_freq = {"1": 1575.42e6, "5": 1176.45e6, "7": 1207.14e6, "8": 1191.795e6, "6": 1278.75e6}
    # BDS
    bds_freq = {"1": 1575.42e6, "2": 1561.098e6, "5": 1176.45e6, "7": 1207.140e6, "8": 1191.795e6, "6": 1268.52e6}
    
    sys = sat_key[0]
    band = sig_id[0]
    freq = None

    if sys in ["G", "J"]:
        freq = gps_freq.get(band)
    elif sys == "E":
        freq = gal_freq.get(band)
    elif sys == "C":
        freq = bds_freq.get(band)
    elif sys == "R":
        # GLONASS FDMA
        # L1 = 1602 + 0.5625 * k
        # L2 = 1246 + 0.4375 * k
        if band == "1":
            freq = 1602.0e6 + 0.5625e6 * fcn
        elif band == "2":
            freq = 1246.0e6 + 0.4375e6 * fcn

    if freq is None:
        return 0.0, 0.0

    return freq, CLIGHT / freq

# -----------------------------------------------------
# Coordinate Transformations
# -----------------------------------------------------

def ecef2lla(pos):
    """
    Convert ECEF XYZ to Lat, Lon, Alt (WGS84).
    """
    x, y, z = pos[0], pos[1], pos[2]
    a = 6378137.0
    e2 = 6.69437999014e-3
    
    b = a * math.sqrt(1 - e2)
    ep = math.sqrt((a**2 - b**2) / b**2)
    p = math.sqrt(x**2 + y**2)
    
    if p == 0:
        return 0.0, 0.0, 0.0

    th = math.atan2(a*z, b*p)
    lon = math.atan2(y, x)
    lat = math.atan2(z + ep*ep*b*(math.sin(th)**3),
                     p - e2*a*(math.cos(th)**3))
    
    # Altitude calculation is approximated here, but usually not needed for Az/El rotation
    # alt = p / math.cos(lat) - a / math.sqrt(1 - e2 * math.sin(lat)**2)
    
    return lat, lon

def rot_ecef2enu(lat, lon):
    """
    Generate Rotation Matrix from ECEF to ENU.
    """
    sl = math.sin(lat)
    cl = math.cos(lat)
    slon = math.sin(lon)
    clon = math.cos(lon)

    R = np.array([
        [-slon,        clon,        0],
        [-sl*clon, -sl*slon,    cl],
        [ cl*clon,  cl*slon,    sl]
    ])
    return R

def ecef2enu(sat_pos, rec_pos):
    """
    Convert satellite position to ENU coordinates relative to receiver.
    """
    # Difference vector in ECEF
    diff = np.array(sat_pos) - np.array(rec_pos)
    
    # Get Receiver Geodetic Lat/Lon
    lat, lon = ecef2lla(rec_pos)
    
    # Get Rotation Matrix
    R = rot_ecef2enu(lat, lon)
    
    # Rotate
    enu = R @ diff
    return enu

def calculate_az_el(sat_ecef, rec_ecef):
    """
    Calculate Azimuth and Elevation. 
    
    Args: sat_ecef: Satellite position [x, y, z] (meters) 
    rec_ecef: Receiver position [x, y, z] (meters) 
    Returns: tuple: (Azimuth [deg], Elevation [deg]) or (0, 0) if error 
    """

    if sat_ecef is None or rec_ecef is None:
        return 0.0, 0.0

    if np.all(np.array(rec_ecef) == 0):
        return 0.0, 0.0

    # ENU vector: [E, N, U]
    e, n, u = ecef2enu(sat_ecef, rec_ecef)

    # ---- Azimuth ----
    az = math.degrees(math.atan2(e, n))  # atan2(E, N)
    if az < 0:
        az += 360.0

    # ---- Elevation ----
    rnorm = math.sqrt(e*e + n*n + u*u)
    el = math.degrees(math.asin(u / rnorm))

    return az, el
