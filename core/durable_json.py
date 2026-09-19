from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

MAX_JSON_BYTES = 16 * 1024 * 1024

try:
    import msvcrt
except ImportError:  # pragma: no cover - Unix fallback
    msvcrt = None


# msvcrt byte-range locks are process-safe, but concurrent threads in the same
# Windows process can still contend on the same lock byte. Keep a process-local
# gate as well so read/modify/write operations remain serialized on Windows.
_WINDOWS_LOCK = threading.RLock()


@contextmanager
def locked_path(path: str | Path) -> Iterator[Path]:
    """Serialize durable read/modify/write operations for one JSON state file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f".{target.name}.lock")
    lock_path.touch(exist_ok=True)
    process_lock = _WINDOWS_LOCK if msvcrt is not None and fcntl is None else None
    if process_lock is not None:
        process_lock.acquire()
    try:
        with lock_path.open("r+", encoding="utf-8") as lock_file:
            if lock_file.seek(0, 2) == 0:
                lock_file.write("0")
                lock_file.flush()
            lock_file.seek(0)
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            elif msvcrt is not None:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                raise OSError("nenhum mecanismo de lock de arquivo suportado neste sistema.")
            try:
                yield target
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        if process_lock is not None:
            process_lock.release()


def read_json(path: str | Path, default: object) -> object:
    """Read one JSON file without a check-then-open filesystem race."""
    target = Path(path)
    try:
        with target.open("rb") as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("arquivo JSON durável grande demais.")
        return json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        return default


def atomic_write_json(path: str | Path, payload: object) -> None:
    """Write JSON atomically and durably; readers see old or new state, never a partial file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
            raise ValueError("payload JSON durável grande demais.")
        with os.fdopen(temporary_fd, "w", encoding="utf-8") as handle:
            temporary_fd = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        if hasattr(os, "O_DIRECTORY"):
            try:
                directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
    finally:
        if temporary_fd != -1:
            try:
                os.close(temporary_fd)
            except OSError:
                pass
        # Cleanup is best-effort. Once os.replace() succeeds, a cleanup
        # failure must never turn a committed durable state into an apparent
        # write failure for the caller. Conversely, when replace fails, the
        # temporary file must not be allowed to mask the original failure.
        try:
            temporary.unlink()
        except OSError:
            pass
