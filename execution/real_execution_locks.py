from __future__ import annotations

import hashlib
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
    """Enforces global REAL lock -> request lock ordering.

    The global lock serializes all REAL dispatches, while the request lock
    prevents a duplicate request from entering the dispatch section. Durable
    state is written only after these locks are held.
    """

    def __init__(self, ledger_path: str | Path) -> None:
        self._root = Path(ledger_path).parent
        self._root.mkdir(parents=True, exist_ok=True)
        self._global_path = self._root / ".real-execution.global.lock"

    @contextmanager
    def acquire(self, request_id: str) -> Iterator[None]:
        if not isinstance(request_id, str) or not request_id.strip():
            raise RealExecutionLockError("request_id inválido para lock REAL.")
        if fcntl is None and msvcrt is None:
            raise RealExecutionLockError(
                "REAL exige lock interprocesso suportado pelo sistema."
            )

        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_path = self._root / f".real-execution.request.{digest}.lock"

        with self._file_lock(self._global_path):
            # This ordering is architectural: global -> request -> persistence.
            with self._file_lock(request_path):
                yield

    @staticmethod
    @contextmanager
    def _file_lock(path: Path) -> Iterator[None]:
        with path.open("a+b") as handle:
            if fcntl is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                except OSError as exc:
                    raise RealExecutionLockError(
                        f"não foi possível adquirir lock interprocesso: {exc}"
                    ) from exc
                try:
                    yield
                finally:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        # Losing the unlock syscall must not be converted into
                        # a second application-level state transition. The OS
                        # will release the descriptor lock when the handle closes.
                        pass
            else:  # pragma: no cover - Windows fallback
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
