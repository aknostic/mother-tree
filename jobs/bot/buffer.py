"""In-memory channel buffer for lazy persistence of silent messages."""
import threading
from collections import defaultdict


class ChannelBuffer:
    """Thread-safe in-memory buffer for channel messages.

    Messages are buffered here instead of written to the database immediately.
    Flushed when: Mother Tree responds, buffer is full, or on periodic interval.
    """

    def __init__(self, max_size: int = 20):
        self._max_size = max_size
        self._buffers: dict[str, list[dict]] = defaultdict(list)
        self._lock = threading.Lock()

    def add(self, channel_id: str, message: dict) -> None:
        with self._lock:
            buf = self._buffers[channel_id]
            buf.append(message)
            if len(buf) > self._max_size:
                self._buffers[channel_id] = buf[-self._max_size:]

    def get(self, channel_id: str) -> list[dict]:
        with self._lock:
            return list(self._buffers.get(channel_id, []))

    def flush(self, channel_id: str) -> list[dict]:
        with self._lock:
            msgs = list(self._buffers.get(channel_id, []))
            self._buffers[channel_id] = []
            return msgs

    def should_flush(self, channel_id: str) -> bool:
        with self._lock:
            return len(self._buffers.get(channel_id, [])) >= self._max_size
