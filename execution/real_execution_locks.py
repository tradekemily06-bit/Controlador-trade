from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None


class RealExecutionLockError(RuntimeError):
    """REAL execution cannot proceed without an inter-process lock."""


class RealExecutionLocks:
    """Enforces global REAL lock -> request lock ordering with safe lock files."""

    def __init__(self, ledger_path: str | Path) -> None:
        self._root = Path(ledger_path).parent
        self._root.mkdir(parents=True, exist_ok=True)
        self._global_path = self._root / ".real-execution.global.lock"

    @contextmanager
    def acquire(self, request_id: str) -> Iterator[None]:
        if not isinstance(request_id, str) or not request_id.strip():
            raise RealExecutionLockError("request_id inválido para lock REAL.")
        if fcntl is None and msvcrt is None:
            raise RealExecutionLockError("REAL exige lock interprocesso suportado pelo sistema.")

        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_path = self._root / f".real-execution.request.{digest}.lock"
        with self._file_lock(self._global_path):
            # Architectural order: global -> request -> durable stores.
            with self._file_lock(request_path):
                yield

    @staticmethod
    @contextmanager
    def _file_lock(path: Path) -> Iterator[None]:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_RDWR
        for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_BINARY"):
            flags |= getattr(os, name, 0)
        try:
            fd = os.open(path, flags, 0o600)
        except OSError as exc:
            raise RealExecutionLockError(
                f"não foi possível abrir lock interprocesso: {exc}"
            ) from exc

        try:
            if not os.path.isfile(path):
                raise RealExecutionLockError("lock REAL não é arquivo regular.")
            if fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                except OSError as exc:
                    raise RealExecutionLockError(
                        f"não foi possível adquirir lock interprocesso: {exc}"
                    ) from exc
                try:
                    yield
                finally:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
            elif msvcrt is not None:  # pragma: no cover - Windows
                with os.fdopen(fd, "r+b", closefd=False) as handle:
                    if os.fstat(fd).st_size == 0:
                        handle.write(b"0")
                        handle.flush()
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    except OSError as exc:
                        raise RealExecutionLockError(
                            "não foi possível adquirir lock interprocesso."
                        ) from exc
                    try:
                        yield
                    finally:
                        try:
                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        except OSError:
                            pass
        finally:
            os.close(fd)
