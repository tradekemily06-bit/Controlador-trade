"""Small cross-process advisory file lock for durable operational state."""
from __future__ import annotations

from contextlib import contextmanager
import os
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
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("não foi possível abrir o lock operacional com segurança") from exc
    try:
        handle = os.fdopen(fd, "a+")
    except OSError as exc:
        os.close(fd)
        raise RuntimeError("não foi possível abrir o lock operacional com segurança") from exc
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError as exc:
            handle.close()
            raise RuntimeError("falha ao adquirir o lock operacional") from exc
        try:
            yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
    except RuntimeError:
        raise
