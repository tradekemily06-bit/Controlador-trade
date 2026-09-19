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
except ImportError:
    fcntl = None

MAX_JSON_BYTES = 16 * 1024 * 1024

try:
    import msvcrt
except ImportError:
    msvcrt = None

_WINDOWS_LOCK = threading.RLock()


@contextmanager
def locked_path(path: str | Path) -> Iterator[Path]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f".{target.name}.lock")
    process_lock = _WINDOWS_LOCK if msvcrt is not None and fcntl is None else None
    if process_lock is not None:
        process_lock.acquire()
    try:
        lock_flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            lock_flags |= os.O_NOFOLLOW
        lock_fd = -1
        try:
            lock_fd = os.open(lock_path, lock_flags, 0o600)
            if hasattr(os, "fchmod"):
                try:
                    os.fchmod(lock_fd, 0o600)
                except OSError:
                    pass
            with os.fdopen(lock_fd, "r+", encoding="utf-8") as lock_file:
                lock_fd = -1
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
            if lock_fd != -1:
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
    finally:
        if process_lock is not None:
            process_lock.release()


def read_json(path: str | Path, default: object) -> object:
    target = Path(path)
    read_fd = -1
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        read_fd = os.open(target, flags)
        with os.fdopen(read_fd, "rb") as handle:
            read_fd = -1
            raw = handle.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("arquivo JSON durável grande demais.")
        return json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        return default
    finally:
        if read_fd != -1:
            try:
                os.close(read_fd)
            except OSError:
                pass


def atomic_write_json(path: str | Path, payload: object) -> None:
    """Atomically persist JSON and report post-replace durability ambiguity."""
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
            directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                # After replace(), failure here means the new bytes are visible
                # but durability of the directory entry is not proven. Report
                # that ambiguity to callers so execution paths fail closed.
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary_fd != -1:
            try:
                os.close(temporary_fd)
            except OSError:
                pass
        try:
            temporary.unlink()
        except OSError:
            pass
