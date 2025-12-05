"""
Handles RTCM stream parsing based on strict RTCM 10403.3 Payload Definitions.
Adapted for pyrtcm's flattened attribute structure.
"""
import numpy as np
from core.data_models import EpochObservation, SatelliteState, SignalData
from core.geo_utils import calculate_az_el, get_freq
import core.BE2pos as BE2pos 
import config
import threading
import math

class RTCMHandler:
    def __init__(self):
        self.ephemeris_cache = {} 
        self.lock = threading.Lock()

    def process_message(self, msg):
        """
        Main entry point for RTCM message processing.
        """
        msg_id = msg.identity

        # --- Ephemeris Processing ---
        if msg_id == "1019":
            self._handle_gps_eph(msg)
        elif msg_id == "1020":
            self._handle_glo_eph(msg)
        elif msg_id in ["1045", "1046"]:
            self._handle_gal_eph(msg)
        elif msg_id in ["1042", "63"]: # 1042 is standard BDS, 63 is draft
            self._handle_bds_eph(msg)
            
        # --- MSM  ---
        elif msg_id[:3] in ["107", "108", "109", "111", "112", "113"]:
            return self._handle_msm_obs(msg)
            
        # --- Station Coordinates ---
        elif msg_id in ["1005", "1006"]:
            if hasattr(msg, "DF025"):
                config.APPROX_REC_POS = [float(msg.DF025), float(msg.DF026), float(msg.DF027)]

    def _update_cache(self, key, new_eph, time_tag_key='Toe'):
        with self.lock:
            if key not in self.ephemeris_cache:
                self.ephemeris_cache[key] = new_eph
                # print(f"[{key}] New Ephemeris loaded. Toe: {new_eph.get(time_tag_key)}")
            else:
                old_eph = self.ephemeris_cache[key]
                if new_eph.get(time_tag_key) != old_eph.get(time_tag_key):
                    self.ephemeris_cache[key] = new_eph
                    # print(f"[{key}] Ephemeris updated. Old Toe: {old_eph.get(time_tag_key)} -> New: {new_eph.get(time_tag_key)}")

    # -------------------------------------------------------------------------
    # GPS Parsing (Msg 1019)
    # -------------------------------------------------------------------------
    def _handle_gps_eph(self, msg):
        """
        Maps RTCM 1019 to GPS Keplerian parameters.
        Reference: DF definitions provided.
        """
        try:
            prn = int(msg.DF009)
            key = f"G{prn:02d}"

            eph = {
                'SatType': 'GPS',
                'PRN': prn,
                'Week': int(msg.DF076)+2048, # GPS Week
                'Toe': float(msg.DF093),     # Reference Time Ephemeris
                'Toc': float(msg.DF081),     # Reference Time Clock
                'IODE': int(msg.DF071),      # Issue of Data, Ephemeris
                
                # 开普勒轨道参数
                'sqrtA': float(msg.DF092),       # Square root of Semi-Major Axis
                'Eccentricity': float(msg.DF090),
                'M0': float(msg.DF088)*math.pi,          # Mean Anomaly
                'omega': float(msg.DF099)*math.pi,       # Argument of Perigee
                'i0': float(msg.DF097)*math.pi,          # Inclination
                'OMEGA0': float(msg.DF095)*math.pi,      # Longitude of Ascending Node
                'Delta_n': float(msg.DF087)*math.pi,     # Mean Motion Diff
                'OMEGA_DOT': float(msg.DF100)*math.pi,   # Rate of Right Ascension
                'IDOT': float(msg.DF079)*math.pi,        # Rate of Inclination
                
                # 摄动参数
                'Cuc': float(msg.DF089),
                'Cus': float(msg.DF091),
                'Crc': float(msg.DF098),
                'Crs': float(msg.DF086),
                'Cic': float(msg.DF094),
                'Cis': float(msg.DF096),
                
                # 钟差参数 (用于后续可能的钟差计算)
                'af0': float(msg.DF084),
                'af1': float(msg.DF083),
                'af2': float(msg.DF082),
                'TGD': float(msg.DF101),
                
                # 健康状况
                'Health': int(msg.DF102)
            }
            
            self._update_cache(key, eph, 'Toe')
            
        except AttributeError as e:
            # print(f"Error parsing GPS 1019: {e}")
            pass

    # -------------------------------------------------------------------------
    # Galileo Parsing (Msg 1045/1046)
    # -------------------------------------------------------------------------
    def _handle_gal_eph(self, msg):
        """
        Maps RTCM 1045/1046 to Galileo parameters.
        """
        try:
            prn = int(msg.DF252)
            key = f"E{prn:02d}"
            
            eph = {
                'SatType': 'GAL',
                'PRN': prn,
                'Week': int(msg.DF289),
                'Toe': float(msg.DF304),
                'Toc': float(msg.DF293),
                'IODNav': int(msg.DF290),
                
                # 轨道参数 (Key名复用 GPS 的标准命名，方便计算函数统一调用)
                'sqrtA': float(msg.DF303),
                'Eccentricity': float(msg.DF301),
                'M0': float(msg.DF299)*math.pi,
                'omega': float(msg.DF310)*math.pi,
                'i0': float(msg.DF308)*math.pi,
                'OMEGA0': float(msg.DF306)*math.pi,
                'Delta_n': float(msg.DF298)*math.pi,
                'OMEGA_DOT': float(msg.DF311)*math.pi,
                'IDOT': float(msg.DF292)*math.pi,
                
                # 摄动
                'Cuc': float(msg.DF300),
                'Cus': float(msg.DF302),
                'Crc': float(msg.DF309),
                'Crs': float(msg.DF297),
                'Cic': float(msg.DF305),
                'Cis': float(msg.DF307),
                
                # 钟差
                'af0': float(msg.DF296),
                'af1': float(msg.DF295),
                'af2': float(msg.DF294),
                'BGD_E1E5a': float(msg.DF312),
                'BGD_E5bE1': float(msg.DF313)
            }
            
            self._update_cache(key, eph, 'Toe')
            
        except AttributeError:
            pass

    # -------------------------------------------------------------------------
    # GLONASS Parsing (Msg 1020)
    # -------------------------------------------------------------------------
    def _handle_glo_eph(self, msg):
        """
        Maps RTCM 1020 to GLONASS Cartesian State Vectors.
        Requires transforming PZ-90 definitions.
        """
        try:
            # DF038: Satellite Slot Number (PRN)
            prn = int(msg.DF038)
            key = f"R{prn:02d}"
            
            # GLONASS 时间处理
            # DF110 (tb) 是 15分钟间隔的索引 (0-96)
            # 为了方便计算，这里将其转换为当天的秒数，或者保留原值并在计算函数中处理
            # 这里我们转换为秒：index * 900
            tb_index = int(msg.DF110)
            tb_seconds = tb_index * 900.0
            
            eph = {
                'SatType': 'GLO',
                'PRN': prn,
                # 注意：计算函数需要 'Tb' 或 'Toe'
                'Tb': tb_seconds,      # Time of day (seconds)
                'tk': float(msg.DF107),# 小时内的时间偏移? 这里的DF107定义是BIT(12)，需确认 pyrtcm 是否解析为数值
                'FreqChannel': int(msg.DF040), # 频率号，对计算频率很重要
                
                # 位置 (km -> m conversion will be done in calculation function or here)
                # pyrtcm 通常返回 km 单位 (因为 scale 是 P2_11 等，结果是 km)
                'X': float(msg.DF112),
                'Y': float(msg.DF115),
                'Z': float(msg.DF118),
                
                # 速度
                'Vx': float(msg.DF111),
                'Vy': float(msg.DF114),
                'Vz': float(msg.DF117),
                
                # 加速度 (Solar/Lunar term)
                'Ax': float(msg.DF113),
                'Ay': float(msg.DF116),
                'Az': float(msg.DF119),
                
                # 钟差
                'TauN': float(msg.DF124), # Satellite clock bias
                'GammaN': float(msg.DF121),# Relative frequency offset
                
                'Health': int(msg.DF104) # Bn (Health)
            }
            
            # GLONASS 更新通常基于 tb
            self._update_cache(key, eph, 'Tb')
            
        except AttributeError:
            pass
            
    # -------------------------------------------------------------------------
    # BeiDou Parsing (Msg 1042)
    # -------------------------------------------------------------------------
    def _handle_bds_eph(self, msg):
        """
        Maps RTCM 1042 to BDS Keplerian parameters.
        Based on RTCM 10403.3 Amendment 2 (or similar) definitions provided.
        """
        try:
            # 根据提供的定义: DF488 是 BDS Satellite ID
            if not hasattr(msg, "DF488"):
                return
            
            prn = int(msg.DF488)
            key = f"C{prn:02d}"
            
            # 构建星历字典
            # 键名必须与 calc_kepler_pos 函数中的变量名一致
            eph = {
                'SatType': 'BDS',
                'PRN': prn,
                'Week': int(msg.DF489),       # DF489: BDS Week Number
                
                # 时间参数
                'Toe': float(msg.DF505),      # DF505: BDS Toe (Time of Ephemeris)
                'Toc': float(msg.DF493),      # DF493: BDS Toc (Time of Clock)
                'AODE': int(msg.DF492),       # DF492: BDS AODE (Age of Data, Ephemeris)
                'AODC': int(msg.DF497),       # DF497: BDS AODC (Age of Data, Clock)
                
                # 开普勒轨道参数
                'sqrtA': float(msg.DF504),        # DF504: BDS A½
                'Eccentricity': float(msg.DF502), # DF502: BDS e
                'M0': float(msg.DF500),           # DF500: BDS M0
                'omega': float(msg.DF511),        # DF511: BDS ω (Argument of Perigee)
                'i0': float(msg.DF509),           # DF509: BDS i0
                'OMEGA0': float(msg.DF507),       # DF507: BDS Ω0
                'Delta_n': float(msg.DF499),      # DF499: BDS ∆n
                'OMEGA_DOT': float(msg.DF512),    # DF512: BDS ΩDOT
                'IDOT': float(msg.DF491),         # DF491: BDS IDOT
                
                # 摄动参数 (Harmonic Corrections)
                'Cuc': float(msg.DF501),      # DF501
                'Cus': float(msg.DF503),      # DF503
                'Crc': float(msg.DF510),      # DF510
                'Crs': float(msg.DF498),      # DF498
                'Cic': float(msg.DF506),      # DF506
                'Cis': float(msg.DF508),      # DF508
                
                # 卫星钟差参数 (a0, a1, a2 -> af0, af1, af2)
                'af0': float(msg.DF496),      # DF496: BDS a0
                'af1': float(msg.DF495),      # DF495: BDS a1
                'af2': float(msg.DF494),      # DF494: BDS a2
                
                # 群波延迟与健康状况
                'TGD1': float(msg.DF513),     # DF513: TGD1
                'TGD2': float(msg.DF514),     # DF514: TGD2
                'Health': int(msg.DF515),     # DF515: SV Health
                
                # 其他信息 (可选，视需要存储)
                'URAI': int(msg.DF490)        # DF490: User Range Accuracy Index
            }

            # 更新缓存
            # 注意：BDS Toe 是周内秒，直接用于判断更新
            self._update_cache(key, eph, 'Toe')
            
        except AttributeError:
            # 捕获可能的解析错误（如消息不完整）
            pass

    def _handle_msm_obs(self, msg):
            """
            Parse RTCM 3.2 MSM7 observation message.
            """
            # Constants
            CLIGHT = 299792458.0
            RANGE_MS = CLIGHT / 1000.0

            msg_id = msg.identity
            sys_prefix = msg_id[:3]

            sys_config = {
                "107": {"sys": "G", "time_df": "DF004", "type": "GPS"},
                "108": {"sys": "R", "time_df": "DF034", "type": "GLO"},
                "109": {"sys": "E", "time_df": "DF248", "type": "GAL"},
                "111": {"sys": "J", "time_df": "DF428", "type": "QZS"},
                "112": {"sys": "C", "time_df": "DF427", "type": "BDS"},
            }

            if sys_prefix not in sys_config:
                return None

            cfg = sys_config[sys_prefix]
            sys_id = cfg["sys"]
            sys_type = cfg["type"] # Used for BE2pos

            if sys_id not in config.TARGET_SYSTEMS:
                return None

            # Epoch Time (Receiver Time in seconds of week/day)
            time_attr = cfg["time_df"]
            if not hasattr(msg, time_attr):
                return None
            epoch_time = getattr(msg, time_attr) / 1000.0
            epoch_data = EpochObservation(gps_time=epoch_time)

            # ------------------------------ Cell Parsing -------------------------------
            cell_prn_map = {}
            unique_prns = set()
            max_cells = 64
            n_cell_found = 0

            for i in range(1, max_cells + 1):
                idx = f"{i:02d}"
                attr = f"CELLPRN_{idx}"
                if hasattr(msg, attr):
                    try:
                        prn = int(getattr(msg, attr))
                        cell_prn_map[i] = prn
                        unique_prns.add(prn)
                        n_cell_found = i
                    except ValueError: continue
                else: break

            if n_cell_found == 0: return None

            sorted_prns = sorted(unique_prns)
            prn_to_sat_idx = {prn: f"{k + 1:02d}" for k, prn in enumerate(sorted_prns)}
            sat_data_cache = {}

            # ------------------------------ Process Satellites -------------------------------
            for i in range(1, n_cell_found + 1):
                if i not in cell_prn_map: continue

                idx = f"{i:02d}"
                prn = cell_prn_map[i]
                sat_idx = prn_to_sat_idx[prn]
                sat_key = f"{sys_id}{prn:02d}"

                # Create SatelliteState
                if sat_key not in epoch_data.satellites:
                    sat_state = SatelliteState(sys_id, prn)
                    epoch_data.satellites[sat_key] = sat_state
                    
                    # ================================================================
                    # NEW LOGIC: Calculate Satellite Position & Az/El
                    # ================================================================
                    if sat_key in self.ephemeris_cache:
                        eph_data = self.ephemeris_cache[sat_key]
                        
                        # 1. Calculate Satellite Position (ECEF) using BE2pos
                        # t_obs_gpst is passed as epoch_time (approximate is fine for initial step)
                        sat_pos = BE2pos.brdc2pos(eph_data, sys_type, epoch_time)
                        
                        if sat_pos is not None:
                            # Store Position
                            sat_state.sat_pos_ecef = sat_pos.tolist()
                            
                            # 2. Calculate Azimuth / Elevation
                            rec_pos = config.APPROX_REC_POS
                            if rec_pos and not np.all(np.array(rec_pos) == 0):
                                az, el = calculate_az_el(sat_pos, rec_pos)
                                sat_state.azimuth = az
                                sat_state.elevation = el
                    # ================================================================

                else:
                    sat_state = epoch_data.satellites[sat_key]

                # Parse Signal Data (Frequency lookup needs refining for GLONASS later)
                try:
                    sig_id = str(getattr(msg, f"CELLSIG_{idx}"))
                except AttributeError: continue
                
                # Simple GLONASS FCN handling could be added here via ephemeris lookup
                fcn = 0 
                if sys_id == 'R' and sat_key in self.ephemeris_cache:
                    # Assuming FreqChannel was stored in handle_glo_eph
                    fcn = self.ephemeris_cache[sat_key].get('FreqChannel', 0)

                freq, _ = get_freq(sig_id, sat_key, fcn)

                # --- Extract Observations (Range, Phase, Doppler, etc.) ---
                if prn not in sat_data_cache:
                    rng_int = getattr(msg, f"DF397_{sat_idx}", None)
                    rng_mod = getattr(msg, f"DF398_{sat_idx}", 0)
                    rate_rough = getattr(msg, f"DF399_{sat_idx}", None)

                    r_sat = 0.0
                    if rng_int is not None and rng_int != 255:
                        r_sat = rng_int * RANGE_MS + rng_mod  * RANGE_MS

                    rr_sat = 0.0
                    if rate_rough is not None and rate_rough != -8192:
                        rr_sat = rate_rough

                    sat_data_cache[prn] = {"r": r_sat, "rr": rr_sat}

                rough_range = sat_data_cache[prn]["r"]
                rough_rate = sat_data_cache[prn]["rr"]

                pr_fine = getattr(msg, f"DF405_{idx}", None)
                pseudorange = 0.0
                if rough_range != 0.0 and pr_fine is not None and pr_fine != -524288:
                    pseudorange = rough_range + pr_fine  * RANGE_MS

                cp_fine = getattr(msg, f"DF406_{idx}", None)
                carrier_phase = 0.0
                if rough_range != 0.0 and cp_fine is not None and cp_fine != -8388608:
                    ph_m = rough_range + cp_fine  * RANGE_MS
                    if freq > 0:
                        carrier_phase = ph_m * freq / CLIGHT

                rr_fine = getattr(msg, f"DF404_{idx}", None)
                doppler = 0.0
                if rough_rate != -8192 and rr_fine is not None and rr_fine != -16384:
                    total_rate = rough_rate + rr_fine * 0.0001
                    if freq > 0:
                        doppler = -total_rate * freq / CLIGHT

                snr = getattr(msg, f"DF408_{idx}", 0)
                lock_time = getattr(msg, f"DF407_{idx}", 0)
                half_cycle = getattr(msg, f"DF420_{idx}", 0)

                if snr > 0 or carrier_phase != 0:
                    obs = SignalData(
                        signal_id=sig_id,
                        pseudorange=float(pseudorange),
                        phase=float(carrier_phase),
                        snr=float(snr),
                        lock_time=int(lock_time),
                        half_cycle=int(half_cycle),
                        doppler=float(doppler),
                    )
                    sat_state.signals[sig_id] = obs

            return epoch_data
