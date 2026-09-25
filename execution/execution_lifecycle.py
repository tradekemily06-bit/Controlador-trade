from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime

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
    """Durable execution state; UNKNOWN is terminal until explicitly reconciled."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, ExecutionLifecycleRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._records = self._decode(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    @classmethod
    def _decode(cls, payload: object) -> dict[str, ExecutionLifecycleRecord]:
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
            cls._validate(record)
            records[record.request_id] = record
        return records

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

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps([
                {"request_id": r.request_id, "state": r.state.value, "updated_at": r.updated_at.isoformat(), "message": r.message}
                for r in self.records()
            ], ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def _mutate_locked(self, mutation) -> None:
        with locked_file(self.path.with_name(f".{self.path.name}.lock")):
            self._load()
            mutation()
            self._save_unlocked()

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps([
                {"request_id": r.request_id, "state": r.state.value, "updated_at": r.updated_at.isoformat(), "message": r.message}
                for r in sorted(self._records.values(), key=lambda item: item.request_id)
            ], ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)

        def mutation() -> None:
            from core.execution_lifecycle_guard import ExecutionLifecycleGuard

            previous = self._records.get(record.request_id)
            transition = ExecutionLifecycleGuard().validate(previous, record.state)
            if not transition.allowed:
                raise ValueError(transition.reason)
            self._records[record.request_id] = record

        self._mutate_locked(mutation)

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        with locked_file(self.path.with_name(f".{self.path.name}.lock")):
            self._load()
            return self._records.get(request_id)

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")

        result: ExecutionLifecycleRecord | None = None

        def mutation() -> None:
            nonlocal result
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state is not ExecutionLifecycleState.UNKNOWN:
                raise ValueError("reconciliação exige estado UNKNOWN.")
            result = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._validate(result)
            self._records[request_id] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        with locked_file(self.path.with_name(f".{self.path.name}.lock")):
            self._load()
            return tuple(self._records[key] for key in sorted(self._records))

