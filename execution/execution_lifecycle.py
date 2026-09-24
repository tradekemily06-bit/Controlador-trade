from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from core.file_lock import locked_file


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
    """Durable execution state with atomic, cross-process transitions."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        from core.execution_lifecycle_guard import ExecutionLifecycleGuard

        self._records: dict[str, ExecutionLifecycleRecord] = {}
        self._guard = ExecutionLifecycleGuard()
        self._load()

    @staticmethod
    def _validate(record: ExecutionLifecycleRecord) -> None:
        if not isinstance(record.request_id, str) or not record.request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(record.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if not isinstance(record.updated_at, datetime):
            raise ValueError("timestamp inválido.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem inválida.")

    def _load_unlocked(self) -> None:
        if not self.path.exists():
            self._records = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError
            records: dict[str, ExecutionLifecycleRecord] = {}
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
                records[record.request_id] = record
            self._records = records
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    def _load(self) -> None:
        with locked_file(self.path.with_name(f".{self.path.name}.lock")):
            self._load_unlocked()

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
                    for r in tuple(self._records[key] for key in sorted(self._records))
                ],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)
        with locked_file(self.path.with_name(f".{self.path.name}.lock")):
            self._load_unlocked()
            transition = self._guard.validate(self._records.get(record.request_id), record.state)
            if not transition.allowed:
                raise ValueError(transition.reason)
            self._records[record.request_id] = record
            self._save_unlocked()

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        self._load()
        return self._records.get(request_id)

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        with locked_file(self.path.with_name(f".{self.path.name}.lock")):
            self._load_unlocked()
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state is not ExecutionLifecycleState.UNKNOWN:
                raise ValueError("reconciliação exige execução UNKNOWN.")
            record = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._validate(record)
            self._records[request_id] = record
            self._save_unlocked()
            return record

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))
