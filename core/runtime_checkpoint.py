from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def process_file_lock(path: str | Path) -> Iterator[None]:
    """Cross-platform process lock for local durable state files."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        import msvcrt
        with lock_path.open("a+b") as lock_file:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover
        raise OSError("bloqueio de processo não suportado neste sistema.") from exc
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


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
        self.path = Path(path)

    def save(self, checkpoint: RuntimeCheckpoint) -> None:
        self._validate(checkpoint)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with process_file_lock(lock_path):
            current = self.load()
            if current is not None:
                if (
                    current.session_id == checkpoint.session_id
                    and checkpoint.last_cycle < current.last_cycle
                ):
                    raise ValueError(
                        "checkpoint obsoleto: last_cycle não pode regredir."
                    )
                if checkpoint.updated_at < current.updated_at:
                    raise ValueError(
                        "checkpoint obsoleto: updated_at não pode regredir."
                    )
            temporary = self.path.with_name(f".{self.path.name}.tmp")
            payload = json.dumps(
                {
                    "session_id": checkpoint.session_id,
                    "last_cycle": checkpoint.last_cycle,
                    "last_request_id": checkpoint.last_request_id,
                    "updated_at": checkpoint.updated_at.isoformat(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            try:
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
            except OSError:
                return
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

    def load(self) -> RuntimeCheckpoint | None:
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
            raise ValueError("checkpoint deve usar timestamp timezone-aware.")
