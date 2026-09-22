"""Small cross-process advisory file lock for durable operational state."""
from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None


@contextmanager
def exclusive_file_lock(path: str | Path) -> Iterator[None]:
    """Serialize a critical section across processes sharing a filesystem.

    Uses the native advisory locking primitive available on the platform.
    If neither supported primitive is available, fail closed.
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if fcntl is not None:
        with lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return

    if msvcrt is not None:
        # msvcrt.locking locks a byte range beginning at the current file
        # position. Keep one durable byte in the lock file and serialize on it.
        with lock_path.open("a+b") as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"\\x00")
                handle.flush()
            handle.seek(0)

            acquired = False
            try:
                while not acquired:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        acquired = True
                    except OSError:
                        time.sleep(0.05)
                yield
            finally:
                if acquired:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    raise RuntimeError("cross-process file locking is unavailable on this platform")
