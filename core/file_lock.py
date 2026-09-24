from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from time import sleep

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None


@contextmanager
def locked_file(path: str | Path):
    """Cross-process exclusive lock; fail closed if the platform has no lock API."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            return

        if msvcrt is None:
            raise RuntimeError("bloqueio de arquivo indisponível nesta plataforma.")

        lock_file.seek(0, 2)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        while True:
            try:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                sleep(0.05)
        try:
            yield
        finally:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
