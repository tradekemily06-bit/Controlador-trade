from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None


@dataclass(frozen=True)
class RuntimeCheckpoint:
    session_id: str
    last_cycle: int
    last_request_id: str | None
    updated_at: datetime


class RuntimeCheckpointStore:
    """Durable checkpoint for safe runtime recovery; never replays an order."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path).expanduser().resolve()

    def _lock_path(self) -> Path:
        return self.path.with_name(f".{self.path.name}.lock")

    @staticmethod
    def _lock(lock_file, *, exclusive: bool) -> None:
        if fcntl is not None:
            mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(lock_file.fileno(), mode)
            return
        if msvcrt is not None:
            lock_file.seek(0, 2)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            return
        raise RuntimeError("plataforma sem mecanismo de lock suportado.")

    @staticmethod
    def _unlock(lock_file) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)

    def save(self, checkpoint: RuntimeCheckpoint) -> None:
        self._validate(checkpoint)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path().open("a+b") as lock_file:
            self._lock(lock_file, exclusive=True)
            try:
                temporary = self.path.with_name(f".{self.path.name}.tmp")
                payload = {
                    "session_id": checkpoint.session_id,
                    "last_cycle": checkpoint.last_cycle,
                    "last_request_id": checkpoint.last_request_id,
                    "updated_at": checkpoint.updated_at.isoformat(),
                }
                with temporary.open("w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
                if os.name != "nt":
                    with self.path.open("rb") as handle:
                        os.fsync(handle.fileno())
                    directory_fd = os.open(self.path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
            finally:
                self._unlock(lock_file)

    def load(self) -> RuntimeCheckpoint | None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path().open("a+b") as lock_file:
            self._lock(lock_file, exclusive=False)
            try:
                if not self.path.exists():
                    return None
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    if not isinstance(data, dict):
                        raise ValueError
                    checkpoint = RuntimeCheckpoint(
                        session_id=data["session_id"],
                        last_cycle=data["last_cycle"],
                        last_request_id=data.get("last_request_id"),
                        updated_at=datetime.fromisoformat(data["updated_at"]),
                    )
                    self._validate(checkpoint)
                    return checkpoint
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise ValueError("checkpoint de runtime inválido.") from exc
            finally:
                self._unlock(lock_file)

    @staticmethod
    def _validate(checkpoint: RuntimeCheckpoint) -> None:
        if not isinstance(checkpoint, RuntimeCheckpoint):
            raise ValueError("checkpoint inválido.")
        if not isinstance(checkpoint.session_id, str) or not checkpoint.session_id.strip():
            raise ValueError("checkpoint inválido.")
        if not isinstance(checkpoint.last_cycle, int) or isinstance(checkpoint.last_cycle, bool) or checkpoint.last_cycle < 0:
            raise ValueError("checkpoint inválido.")
        if checkpoint.last_request_id is not None and (
            not isinstance(checkpoint.last_request_id, str) or not checkpoint.last_request_id.strip()
        ):
            raise ValueError("request_id do checkpoint inválido.")
        if (
            not isinstance(checkpoint.updated_at, datetime)
            or checkpoint.updated_at.tzinfo is None
            or checkpoint.updated_at.utcoffset() is None
        ):
            raise ValueError("timestamp do checkpoint deve ser timezone-aware.")
