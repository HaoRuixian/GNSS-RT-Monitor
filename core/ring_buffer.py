import threading
from collections import deque
from typing import Optional, Any


class RingBuffer:
    """
    Thread-safe ring buffer implementation for efficient data transfer between I/O and processing threads.
    """
    def __init__(self, maxsize: int = 1000):
        """
        Initialize the ring buffer.
        
        Args:
            maxsize: The maximum size of the buffer. If the buffer is full, the oldest data is discarded.
        """
        self.maxsize = maxsize
        self.buffer = deque(maxlen=maxsize)
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock)
        self.not_full = threading.Condition(self.lock)
        self.closed = False
        
    def put(self, item: Any, block: bool = False, timeout: Optional[float] = None) -> bool:
        """
        Write data to the buffer (non-blocking mode, high priority).
        
        Args:
            item: The data to write.
            block: Whether to block the thread until the buffer is not full (default is False, non-blocking).
            timeout: The timeout time (only valid when block=True).
            
        Returns:
            bool: Whether the data is successfully written.
        """
        with self.not_full:
            if self.closed:
                return False
                
            # Non-blocking mode: If the buffer is full, discard the oldest data (ring buffer feature).
            if not block:
                # If the buffer is full, deque will discard the oldest data.
                self.buffer.append(item)
                self.not_empty.notify()
                return True
            else:
                # Blocking mode: Wait for space to be available.
                if len(self.buffer) >= self.maxsize:
                    if not self.not_full.wait(timeout):
                        return False
                self.buffer.append(item)
                self.not_empty.notify()
                return True
    
    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[Any]:
        """
        Read data from the buffer.
        
        Args:
            block: Whether to block the thread until the buffer is not empty (default is True).
            timeout: The timeout time.
            
        Returns:
            The data read from the buffer. If the buffer is empty and the non-blocking mode is used, return None.
        """
        with self.not_empty:
            if not block:
                if len(self.buffer) == 0:
                    return None
                item = self.buffer.popleft()
                self.not_full.notify()
                return item
            else:
                while len(self.buffer) == 0:
                    if self.closed:
                        return None
                    if not self.not_empty.wait(timeout):
                        return None
                item = self.buffer.popleft()
                self.not_full.notify()
                return item
    
    def qsize(self) -> int:
        """Return the current size of the buffer."""
        with self.lock:
            return len(self.buffer)
    
    def empty(self) -> bool:
        """Check if the buffer is empty."""
        with self.lock:
            return len(self.buffer) == 0
    
    def full(self) -> bool:
        """Check if the buffer is full."""
        with self.lock:
            return len(self.buffer) >= self.maxsize
    
    def close(self):
        with self.lock:
            self.closed = True
            self.not_empty.notify_all()
            self.not_full.notify_all()
    
    def clear(self):
        with self.lock:
            self.buffer.clear()
            self.not_full.notify_all()
