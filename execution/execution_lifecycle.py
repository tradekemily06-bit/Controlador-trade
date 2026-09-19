from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None
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
                    raise ValueError("request_id duplicado no ciclo persistido.")
                loaded[record.request_id] = record
            self._records = loaded
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    @staticmethod
    def _validate(record: ExecutionLifecycleRecord) -> None:
        if not isinstance(record.request_id, str) or not record.request_id.strip() or len(record.request_id.strip()) > 128:
            raise ValueError("request_id inválido.")
        if not isinstance(record.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if not isinstance(record.updated_at, datetime):
            raise ValueError("timestamp inválido.")
        if not isinstance(record.message, str) or len(record.message) > 4096:
            raise ValueError("mensagem inválida.")

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)

        def mutation() -> None:
            previous = self._records.get(record.request_id)
            if previous is not None:
                if previous.state is ExecutionLifecycleState.UNKNOWN and record.state is not ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("execução UNKNOWN requer reconciliação explícita.")
                if previous.state in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
                    raise ValueError("estado terminal não pode ser sobrescrito.")
                if previous.state is ExecutionLifecycleState.PENDING and record.state is ExecutionLifecycleState.PENDING:
                    raise ValueError("execução PENDING já existe.")
            self._records[record.request_id] = record

        self._mutate_locked(mutation)

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id.strip()) > 128:
            raise ValueError("request_id inválido.")
        self._load()
        return self._records.get(request_id)

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        result: ExecutionLifecycleRecord | None = None

        def mutation() -> None:
            nonlocal result
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state not in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN):
                raise ValueError("somente PENDING ou UNKNOWN pode ser reconciliado.")
            result = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._validate(result)
            self._records[request_id] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))

    def blocking_request_ids(self) -> tuple[str, ...]:
        self._load()
        return tuple(sorted(
            request_id
            for request_id, record in self._records.items()
            if record.state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN)
        ))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps([
                {"request_id": r.request_id, "state": r.state.value, "updated_at": r.updated_at.isoformat(), "message": r.message}
                for r in tuple(self._records.values())
            ], ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def _mutate_locked(self, mutation) -> None:
        """Serialize cross-process read/modify/write on Linux deployments."""
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                self._load()
                mutation()
                self._save()
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
