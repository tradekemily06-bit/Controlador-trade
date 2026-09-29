from __future__ import annotations

from contextlib import contextmanager
from threading import RLock


_LOCK = RLock()


@contextmanager
def mt5_session_lock():
    """Serialize access to the process-wide MetaTrader5 Python session.

    The MT5 Python package exposes one terminal session per process. The
    ecosystem has concurrent market-data, HTTP, risk-state and outcome paths,
    so initialize/shutdown blocks must not overlap across threads.
    """
    with _LOCK:
        yield
