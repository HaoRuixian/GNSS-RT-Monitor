import threading
import time
from PyQt5.QtCore import QObject, pyqtSignal
from pyrtcm import RTCMReader

from core.ntrip_client import NtripClient

class StreamSignals(QObject):
    log_signal = pyqtSignal(str)
    epoch_signal = pyqtSignal(object)
    status_signal = pyqtSignal(str, bool)

class NtripWorker(threading.Thread):
    def __init__(self, name, settings, handler, signals):
        super().__init__()
        self.name = name
        self.settings = settings
        self.handler = handler
        self.signals = signals
        self.daemon = True
        self.running = True
        self.client = None

    def run(self):
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
                self.signals.log_signal.emit(f"[{self.name}] Connecting...")
                sock = self.client.connect()
                if not sock:
                    self.signals.log_signal.emit(f"[{self.name}] Failed. Retry 3s...")
                    self.signals.status_signal.emit(self.name, False)
                    for _ in range(30): 
                        if not self.running: return
                        time.sleep(0.1)
                    continue

                self.signals.log_signal.emit(f"[{self.name}] Connected.")
                self.signals.status_signal.emit(self.name, True)
                reader = RTCMReader(sock)

                for raw, msg in reader:
                    if not self.running: break
                    if msg is None: continue
                    epoch_data = self.handler.process_message(msg)
                    if epoch_data:
                        self.signals.epoch_signal.emit(epoch_data)

            except Exception as e:
                self.signals.log_signal.emit(f"[{self.name}] Error: {str(e)}")
                self.signals.status_signal.emit(self.name, False)
            finally:
                if self.client: self.client.close()
                self.signals.status_signal.emit(self.name, False)
                time.sleep(2)

    def stop(self):
        self.running = False

