from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from core.file_lock import exclusive_file_lock


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

        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_path = self._root / f".real-execution.request.{digest}.lock"

        try:
            with exclusive_file_lock(self._global_path):
                # This ordering is architectural: global -> request -> persistence.
                with exclusive_file_lock(request_path):
                    yield
        except OSError as exc:
            raise RealExecutionLockError(str(exc)) from exc
