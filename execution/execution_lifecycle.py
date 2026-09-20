from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from core.file_lock import exclusive_file_lock
from datetime import datetime


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
    """Durable execution state with atomic, process-safe read/modify/write semantics."""

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
                if record.request_id in records:
                    raise ValueError("request_id duplicado no ciclo persistido.")
                records[record.request_id] = record
            self._records = records
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    @staticmethod
    def _validate(record: ExecutionLifecycleRecord) -> None:
        if not isinstance(record.request_id, str) or not record.request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(record.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if not isinstance(record.updated_at, datetime) or record.updated_at.tzinfo is None:
            raise ValueError("timestamp deve ser timezone-aware.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem inválida.")

    @staticmethod
    def _allowed(current: ExecutionLifecycleState | None, target: ExecutionLifecycleState) -> bool:
        if current is None:
            return target is ExecutionLifecycleState.PENDING
        return target in {
            ExecutionLifecycleState.PENDING: {
                ExecutionLifecycleState.ACCEPTED,
                ExecutionLifecycleState.REJECTED,
                ExecutionLifecycleState.UNKNOWN,
            },
            ExecutionLifecycleState.UNKNOWN: set(),
            ExecutionLifecycleState.ACCEPTED: set(),
            ExecutionLifecycleState.REJECTED: set(),
        }.get(current, set())

    def _mutate_locked(self, mutation):
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with exclusive_file_lock(lock_path):
                self._load()
                result = mutation()
                self._save()
                return result


    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)

        def mutation() -> None:
            previous = self._records.get(record.request_id)
            if not self._allowed(previous.state if previous else None, record.state):
                if previous is not None and previous.state is ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("execução UNKNOWN requer reconciliação explícita.")
                raise ValueError(
                    f"transição inválida de {previous.state.value if previous else 'NONE'} para {record.state.value}."
                )
            self._records[record.request_id] = record

        self._mutate_locked(mutation)

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
        self._validate(ExecutionLifecycleRecord(request_id, state, updated_at, message))

        def mutation() -> ExecutionLifecycleRecord:
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state not in (ExecutionLifecycleState.UNKNOWN, ExecutionLifecycleState.PENDING):
                raise ValueError("reconciliação só pode concluir UNKNOWN/PENDING.")
            record = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._records[request_id] = record
            return record

        return self._mutate_locked(mutation)

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = [
            {
                "request_id": r.request_id,
                "state": r.state.value,
                "updated_at": r.updated_at.isoformat(),
                "message": r.message,
            }
            for r in self.records()
        ]
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
