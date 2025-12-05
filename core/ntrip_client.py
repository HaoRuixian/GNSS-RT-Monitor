"""
NTRIP Client implementation using sockets.
"""
import socket
import base64
import time
import sys

class NtripClient:
    def __init__(self, host, port, mountpoint, user, password):
        self.host = host
        self.port = port
        self.mountpoint = mountpoint
        self.auth = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.sock = None

    def connect(self):
        """Establish TCP connection and send NTRIP GET request."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((self.host, self.port))
            
            headers = (
                f"GET /{self.mountpoint} HTTP/1.0\r\n"
                f"User-Agent: NTRIP Python/GNSS-IR\r\n"
                f"Authorization: Basic {self.auth}\r\n"
                f"\r\n"
            )
            self.sock.sendall(headers.encode())
            
            # Check response
            response = b""
            while b"\n" not in response:
                chunk = self.sock.recv(1024)
                if not chunk:
                    raise ConnectionError("Server closed connection.")
                response += chunk

            print("Header:", response.decode(errors="ignore"))

            
            if b"200 OK" in response:
                print(f"[NTRIP] Connected to {self.mountpoint}")
                return self.sock
            else:
                print(f"[NTRIP] Failed: {response.decode(errors='ignore')}")
                return None
                
        except Exception as e:
            print(f"[NTRIP] Connection Error: {e}")
            return None

    def close(self):
        if self.sock:
            self.sock.close()