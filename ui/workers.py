import threading
import time
import os
import sys
from queue import Queue
from PyQt6.QtCore import QObject, pyqtSignal
from pyrtcm import RTCMReader

from core.ntrip_client import NtripClient
from core.ring_buffer import RingBuffer


class StreamSignals(QObject):
    log_signal = pyqtSignal(str)
    epoch_signal = pyqtSignal(object)  # 发送处理后的epoch数据
    status_signal = pyqtSignal(str, bool)


class IOThread(threading.Thread):
    def __init__(self, name: str, settings: dict, ring_buffer: RingBuffer, signals: StreamSignals):
        super().__init__()
        self.name = name
        self.settings = settings
        self.ring_buffer = ring_buffer
        self.signals = signals
        self.daemon = True
        self.running = True
        self.client = None
        self.msg_count = 0
        self.last_log_time = time.time()
        
    def run(self):
        if sys.platform == 'win32':
            try:
                import ctypes
                # THREAD_PRIORITY_HIGHEST = 2
                kernel32 = ctypes.windll.kernel32
                thread_handle = kernel32.OpenThread(0x1F03FF, False, kernel32.GetCurrentThreadId())
                if thread_handle:
                    kernel32.SetThreadPriority(thread_handle, 2)  # THREAD_PRIORITY_HIGHEST
                    kernel32.CloseHandle(thread_handle)
            except:
                pass
        try:
            self.client = NtripClient(
                self.settings['host'], int(self.settings['port']),
                self.settings['mountpoint'], self.settings['user'], self.settings['password']
            )
        except Exception as e:
            self.signals.log_signal.emit(f"[{self.name}] Config Error: {e}")
            return

        while self.running:
            try:
                host_port = f"{self.settings['host']}:{self.settings['port']}"
                mount = self.settings['mountpoint']
                self.signals.log_signal.emit(f"[{self.name}] Connecting to {host_port}/{mount}...")
                sock = self.client.connect()
                if not sock:
                    self.signals.log_signal.emit(f"[{self.name}] Connection failed. Retry in 3s...")
                    self.signals.status_signal.emit(self.name, False)
                    for _ in range(30): 
                        if not self.running: return
                        time.sleep(0.1)
                    continue

                self.signals.log_signal.emit(f"[{self.name}] Connected to {host_port}/{mount}")
                self.signals.status_signal.emit(self.name, True)
                reader = RTCMReader(sock)
                self.msg_count = 0
                self.last_log_time = time.time()

                # I/O线程：只负责读取原始消息并写入缓冲区，不做任何处理
                for raw, msg in reader:
                    if not self.running: break
                    if msg is None: continue
                    
                    self.msg_count += 1
                    # 每10秒输出一次统计
                    now = time.time()
                    if now - self.last_log_time >= 10.0:
                        rate = self.msg_count / (now - self.last_log_time)
                        self.signals.log_signal.emit(f"[{self.name}] Receiving: {self.msg_count} msgs, {rate:.1f} msg/s")
                        self.msg_count = 0
                        self.last_log_time = now
                    
                    # 非阻塞写入：如果缓冲区满，自动丢弃最旧的数据
                    self.ring_buffer.put((raw, msg), block=False)

            except Exception as e:
                self.signals.log_signal.emit(f"[{self.name}] Error: {str(e)}")
                self.signals.status_signal.emit(self.name, False)
            finally:
                if self.client: 
                    self.client.close()
                    self.signals.log_signal.emit(f"[{self.name}] Connection closed")
                self.signals.status_signal.emit(self.name, False)
                time.sleep(2)

    def stop(self):
        """停止I/O线程"""
        self.running = False


class DataProcessingThread(threading.Thread):
    def __init__(self, name: str, ring_buffer: RingBuffer, handler, signals: StreamSignals):
        super().__init__()
        self.name = name
        self.ring_buffer = ring_buffer
        self.handler = handler
        self.signals = signals
        self.daemon = True
        self.running = True
        self.epoch_count = 0
        self.msg_count = 0
        self.msg_types = {}  # Track message types
        self.eph_count = 0
        self.last_log_time = time.time()
        self.first_epoch = True
        
    def run(self):
        self.signals.log_signal.emit(f"[{self.name}] Processing thread started")
        while self.running:
            try:
                data = self.ring_buffer.get(block=True, timeout=0.1)
                
                if data is None:
                    if self.ring_buffer.closed:
                        self.signals.log_signal.emit(f"[{self.name}] Buffer closed, stopping")
                        break
                    continue
                
                raw, msg = data
                self.msg_count += 1
                
                # Track message types
                msg_id = getattr(msg, 'identity', 'UNKNOWN')
                self.msg_types[msg_id] = self.msg_types.get(msg_id, 0) + 1
                
                # Track ephemeris messages
                if msg_id in ["1019", "1020", "1042", "1045", "1046", "63"]:
                    self.eph_count += 1
                
                # 处理RTCM消息
                epoch_data = self.handler.process_message(msg)
                
                # 如果处理成功，发送信号到UI线程
                if epoch_data:
                    self.epoch_count += 1
                    if self.first_epoch:
                        n_sats = len(epoch_data.satellites)
                        n_sigs = sum(len(sat.signals) for sat in epoch_data.satellites.values())
                        self.signals.log_signal.emit(
                            f"[{self.name}] First epoch received: {n_sats} satellites, {n_sigs} signals"
                        )
                        self.first_epoch = False
                    self.signals.epoch_signal.emit(epoch_data)
                
                # 每30秒输出一次统计
                now = time.time()
                if now - self.last_log_time >= 30.0:
                    epoch_rate = self.epoch_count / (now - self.last_log_time)
                    msg_rate = self.msg_count / (now - self.last_log_time)
                    top_msgs = sorted(self.msg_types.items(), key=lambda x: x[1], reverse=True)[:5]
                    msg_summary = ', '.join([f"#{k}({v})" for k, v in top_msgs])
                    self.signals.log_signal.emit(
                        f"[{self.name}] Stats: {self.msg_count} msgs ({msg_rate:.1f}/s), "
                        f"{self.epoch_count} epochs ({epoch_rate:.2f}/s), "
                        f"{self.eph_count} eph, Top: {msg_summary}"
                    )
                    self.msg_count = 0
                    self.epoch_count = 0
                    self.eph_count = 0
                    self.msg_types.clear()
                    self.last_log_time = now
                    
            except Exception as e:
                self.signals.log_signal.emit(f"[{self.name}] Processing Error: {str(e)}")
                import traceback
                self.signals.log_signal.emit(f"[{self.name}] Traceback: {traceback.format_exc()}")
                time.sleep(0.01) 
    
    def stop(self):
        self.running = False
