from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None


class FileLockError(OSError):
    """Raised when a local inter-process lock cannot be acquired safely."""


def _open_lock(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_RDWR
    for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_BINARY"):
        flags |= getattr(os, name, 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise FileLockError(f"não foi possível abrir lock seguro: {exc}") from exc
    try:
        if not os.path.isfile(path):
            raise FileLockError("lock não é arquivo regular.")
        if os.name == "nt" and os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
            os.fsync(fd)
        return fd
    except Exception:
        os.close(fd)
        raise


@contextmanager
def exclusive_file_lock(path: str | Path) -> Iterator[None]:
    """Acquire a cross-platform local lock without following a lock-file symlink."""
    lock_path = Path(path)
    fd = _open_lock(lock_path)
    handle = None
    try:
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
            except OSError as exc:
                raise FileLockError(f"não foi possível adquirir lock: {exc}") from exc
        elif msvcrt is not None:
            handle = os.fdopen(fd, "r+b", closefd=False)
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            except OSError as exc:
                raise FileLockError("não foi possível adquirir lock interprocesso.") from exc
        else:
            raise FileLockError("sistema sem mecanismo de lock interprocesso suportado.")
        yield
    finally:
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        elif msvcrt is not None and handle is not None:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            handle.close()
        os.close(fd)
