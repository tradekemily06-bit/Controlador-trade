from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from core.file_lock import exclusive_file_lock

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
    """Durable runtime checkpoint; never acts as execution authority.

    Checkpoint writes are serialized across processes and published with
    atomic replacement. A torn/partial checkpoint therefore cannot become a
    valid recovery input; invalid persisted state fails closed on load.
    """

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)

    def save(self, checkpoint: RuntimeCheckpoint) -> None:
        self._validate(checkpoint)
        with self._mutation_lock():
            self._save_unlocked(checkpoint)

    @staticmethod
    def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("objeto JSON do checkpoint contém chave duplicada.")
            result[key] = value
        return result

    def load(self) -> RuntimeCheckpoint | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(
                self.path.read_text(encoding="utf-8"),
                object_pairs_hook=self._unique_json_object,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"constante JSON não permitida: {value}")),
            )
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
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError("checkpoint de runtime inválido.") from exc

    @staticmethod
    def _validate(checkpoint: RuntimeCheckpoint) -> None:
        if not isinstance(checkpoint, RuntimeCheckpoint):
            raise ValueError("checkpoint inválido.")
        if not isinstance(checkpoint.session_id, str) or not checkpoint.session_id.strip():
            raise ValueError("checkpoint inválido.")
        if (
            not isinstance(checkpoint.last_cycle, int)
            or isinstance(checkpoint.last_cycle, bool)
            or checkpoint.last_cycle < 0
        ):
            raise ValueError("checkpoint inválido.")
        if checkpoint.last_request_id is not None and (
            not isinstance(checkpoint.last_request_id, str)
            or not checkpoint.last_request_id.strip()
            or checkpoint.last_request_id != checkpoint.last_request_id.strip()
        ):
            raise ValueError("request_id do checkpoint inválido.")
        if (
            not isinstance(checkpoint.updated_at, datetime)
            or checkpoint.updated_at.tzinfo is None
            or checkpoint.updated_at.utcoffset() is None
        ):
            raise ValueError("checkpoint timestamp deve ser timezone-aware.")

    @contextmanager
    def _mutation_lock(self) -> Iterator[None]:
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with exclusive_file_lock(lock_path):
            yield

    def _save_unlocked(self, checkpoint: RuntimeCheckpoint) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {
            "session_id": checkpoint.session_id,
            "last_cycle": checkpoint.last_cycle,
            "last_request_id": checkpoint.last_request_id,
            "updated_at": checkpoint.updated_at.isoformat(),
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        try:
            # Re-open read/write so fsync() is applied to an actual writable
            # file descriptor, not a read-only stream. If publication fails,
            # the old durable target remains authoritative.
            with temporary.open("r+b") as durable_file:
                durable_file.flush()
                os.fsync(durable_file.fileno())
            os.replace(temporary, self.path)
        finally:
            # A crash can leave the temporary artifact behind. It is never
            # consulted as authority, and cleanup must not mask the primary
            # persistence error.
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
        if fcntl is not None:
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
