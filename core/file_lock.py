"""Small cross-process advisory file lock for durable operational state."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


@contextmanager
def exclusive_file_lock(path: str | Path) -> Iterator[None]:
    """Serialize a critical section across processes sharing a filesystem.

    Operational state must never silently fall back to process-local locking:
    if the platform cannot provide an OS-level advisory lock, fail closed.
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        raise RuntimeError("cross-process file locking is unavailable on this platform")
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
