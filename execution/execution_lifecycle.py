from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime

from core.file_lock import exclusive_file_lock


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

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(self.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if not isinstance(self.updated_at, datetime) or self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("timestamp deve ser timezone-aware.")
        if not isinstance(self.message, str):
            raise ValueError("mensagem inválida.")


class ExecutionLifecycleStore:
    """Durable execution state; UNKNOWN is terminal until explicitly reconciled."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, ExecutionLifecycleRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._records = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError
            loaded: dict[str, ExecutionLifecycleRecord] = {}
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
                if record.request_id in loaded:
                    raise ValueError("request_id duplicado no ciclo de execução persistido.")
                loaded[record.request_id] = record
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc
        self._records = loaded

    @staticmethod
    def _validate(record: ExecutionLifecycleRecord) -> None:
        if not isinstance(record.request_id, str) or not record.request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(record.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if not isinstance(record.updated_at, datetime) or record.updated_at.tzinfo is None or record.updated_at.utcoffset() is None:
            raise ValueError("timestamp deve ser timezone-aware.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem inválida.")

    @staticmethod
    def _allowed_transition(previous: ExecutionLifecycleState, current: ExecutionLifecycleState) -> bool:
        """Allow only monotonic lifecycle progress; reconciliation is the only exit from UNKNOWN."""
        allowed = {
            ExecutionLifecycleState.PENDING: {
                ExecutionLifecycleState.PENDING,
                ExecutionLifecycleState.ACCEPTED,
                ExecutionLifecycleState.REJECTED,
                ExecutionLifecycleState.UNKNOWN,
            },
            ExecutionLifecycleState.ACCEPTED: {ExecutionLifecycleState.ACCEPTED},
            ExecutionLifecycleState.REJECTED: {ExecutionLifecycleState.REJECTED},
            ExecutionLifecycleState.UNKNOWN: {ExecutionLifecycleState.UNKNOWN},
        }
        return current in allowed[previous]

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)
        with exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock")):
            self._load()
            previous = self._records.get(record.request_id)
            if previous is not None and not self._allowed_transition(previous.state, record.state):
                if previous.state is ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("execução UNKNOWN requer reconciliação explícita.")
                raise ValueError(
                    f"transição de ciclo inválida de {previous.state.value} para {record.state.value}."
                )
            candidate = dict(self._records)
            candidate[record.request_id] = record
            self._save(candidate)
            self._records = candidate

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        with exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock")):
            self._load()
            return self._records.get(request_id)

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        record = ExecutionLifecycleRecord(request_id, state, updated_at, message)
        self._validate(record)
        with exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock")):
            self._load()
            if self._records.get(request_id) is None:
                raise ValueError("execução não encontrada.")
            previous = self._records[request_id]
            if previous.state is not ExecutionLifecycleState.UNKNOWN:
                raise ValueError("reconciliação explícita exige estado UNKNOWN.")
            candidate = dict(self._records)
            candidate[request_id] = record
            self._save(candidate)
            self._records = candidate
            return record

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        with exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock")):
            self._load()
            return tuple(self._records[key] for key in sorted(self._records))

    @staticmethod
    def _serialize(records: dict[str, ExecutionLifecycleRecord]) -> str:
        return json.dumps([
            {"request_id": r.request_id, "state": r.state.value, "updated_at": r.updated_at.isoformat(), "message": r.message}
            for r in (records[key] for key in sorted(records))
        ], ensure_ascii=False, indent=2, sort_keys=True)

    def _save(self, records: dict[str, ExecutionLifecycleRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(self._serialize(records), encoding="utf-8")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        directory_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
