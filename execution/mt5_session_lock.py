from __future__ import annotations

from functools import wraps
from threading import RLock


# MetaTrader5's Python package controls one active terminal session per process.
# All adapters must serialize initialization, reads, writes, and shutdown against it.
MT5_TERMINAL_SESSION_LOCK = RLock()


def serialized_mt5_session(method):
    """Hold the process-wide terminal lock for the complete adapter operation."""
    @wraps(method)
    def wrapped(*args, **kwargs):
        with MT5_TERMINAL_SESSION_LOCK:
            return method(*args, **kwargs)
    return wrapped
