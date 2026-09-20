from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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


class ExecutionLifecycleState(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExecutionLifecycleRecord:
    request_id: str
    state: ExecutionLifecycleState
    updated_at: datetime
    message: str = ""


class ExecutionLifecycleStore:
    """Durable lifecycle projection; UNKNOWN is terminal until explicit reconciliation.

    Reads refresh from disk so separate processes do not rely on constructor-time
    snapshots. Writes use an inter-process lock and atomic replacement.
    """

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, ExecutionLifecycleRecord] = {}
        self._load()

    @staticmethod
    def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("objeto JSON do lifecycle contém chave duplicada.")
            result[key] = value
        return result

    def _load(self) -> None:
        self._records = {}
        if not self.path.exists():
            return
        try:
            payload = json.loads(
                self.path.read_text(encoding="utf-8"),
                object_pairs_hook=self._unique_json_object,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"constante JSON não permitida: {value}")),
            )
            if not isinstance(payload, list):
                raise ValueError
            seen_request_ids: set[str] = set()
            for item in payload:
                if not isinstance(item, dict):
                    raise ValueError
                record = ExecutionLifecycleRecord(
                    request_id=item["request_id"],
                    state=ExecutionLifecycleState(item["state"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                    message=item.get("message", ""),
                )
                self._validate(record)
                if record.request_id in seen_request_ids:
                    raise ValueError("request_id duplicado no lifecycle persistido.")
                seen_request_ids.add(record.request_id)
                self._records[record.request_id] = record
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    @staticmethod
    def _validate(record: ExecutionLifecycleRecord) -> None:
        if (
            not isinstance(record.request_id, str)
            or not record.request_id.strip()
            or record.request_id != record.request_id.strip()
        ):
            raise ValueError("request_id inválido ou não canônico.")
        if not isinstance(record.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if (
            not isinstance(record.updated_at, datetime)
            or record.updated_at.tzinfo is None
            or record.updated_at.utcoffset() is None
        ):
            raise ValueError("timestamp deve ser timezone-aware.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem inválida.")

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)
        with self._mutation_lock():
            self._load()
            previous = self._records.get(record.request_id)
            if previous is not None:
                if previous.state is ExecutionLifecycleState.UNKNOWN and record.state is not ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("execução UNKNOWN requer reconciliação explícita.")
                self._validate_transition(previous.state, record.state)
            self._records[record.request_id] = record
            self._save_unlocked()

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        self._load()
        return self._records.get(request_id)

    def reconcile(
        self,
        request_id: str,
        state: ExecutionLifecycleState,
        *,
        updated_at: datetime,
        message: str = "",
    ) -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        with self._mutation_lock():
            self._load()
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state not in (
                ExecutionLifecycleState.UNKNOWN,
                ExecutionLifecycleState.PENDING,
            ):
                raise ValueError("execução não está em estado reconciliável.")
            record = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._validate(record)
            self._records[request_id] = record
            self._save_unlocked()
            return record

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))

    @staticmethod
    def _validate_transition(
        current: ExecutionLifecycleState,
        target: ExecutionLifecycleState,
    ) -> None:
        allowed = {
            ExecutionLifecycleState.PENDING: {
                ExecutionLifecycleState.PENDING,
                ExecutionLifecycleState.ACCEPTED,
                ExecutionLifecycleState.REJECTED,
                ExecutionLifecycleState.UNKNOWN,
            },
            ExecutionLifecycleState.UNKNOWN: {ExecutionLifecycleState.UNKNOWN},
            ExecutionLifecycleState.ACCEPTED: {ExecutionLifecycleState.ACCEPTED},
            ExecutionLifecycleState.REJECTED: {ExecutionLifecycleState.REJECTED},
        }
        if target not in allowed[current]:
            raise ValueError(
                f"transição Lifecycle inválida: {current.value} -> {target.value}."
            )

    @contextmanager
    def _mutation_lock(self) -> Iterator[None]:
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with exclusive_file_lock(lock_path):
            yield

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(
                [
                    {
                        "request_id": r.request_id,
                        "state": r.state.value,
                        "updated_at": r.updated_at.isoformat(),
                        "message": r.message,
                    }
                    for r in self.records_snapshot()
                ],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
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

    def records_snapshot(self) -> tuple[ExecutionLifecycleRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))
