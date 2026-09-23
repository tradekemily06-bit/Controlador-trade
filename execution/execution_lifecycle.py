from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime

try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
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
    """Durable execution state with cross-process serialized read/modify/write."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, ExecutionLifecycleRecord] = {}
        self._load()

    def _lock_file(self):
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        elif msvcrt is not None:
            handle.seek(0)
            handle.write("0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return handle

    @staticmethod
    def _unlock_file(handle) -> None:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        handle.close()

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
                if record.request_id in records:
                    raise ValueError("request_id duplicado no ciclo persistido")
                records[record.request_id] = record
            self._records = records
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    def _load(self) -> None:
        handle = self._lock_file()
        try:
            self._load_unlocked()
        finally:
            self._unlock_file(handle)

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

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(json.dumps([
            {"request_id": r.request_id, "state": r.state.value,
             "updated_at": r.updated_at.isoformat(), "message": r.message}
            for r in self._records.values()
        ], ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def _mutate(self, mutation) -> None:
        handle = self._lock_file()
        try:
            self._load_unlocked()
            mutation()
            self._save_unlocked()
        finally:
            self._unlock_file(handle)

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)
        def mutation() -> None:
            previous = self._records.get(record.request_id)
            if previous is not None:
                if previous.state is ExecutionLifecycleState.UNKNOWN and record.state is not ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("execução UNKNOWN requer reconciliação explícita.")
                if previous.state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.ACCEPTED) and record.state is not ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("request_id já possui ciclo ativo; replay concorrente recusado.")
                if previous.state is ExecutionLifecycleState.REJECTED and record.state is not ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("request_id já possui ciclo terminal; replay recusado.")
            self._records[record.request_id] = record
        self._mutate(mutation)

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        handle = self._lock_file()
        try:
            self._load_unlocked()
            return self._records.get(request_id)
        finally:
            self._unlock_file(handle)

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        record = ExecutionLifecycleRecord(request_id, state, updated_at, message)
        self._validate(record)
        def mutation() -> None:
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state not in (ExecutionLifecycleState.UNKNOWN, ExecutionLifecycleState.PENDING):
                raise ValueError("execução não está em estado reconciliável.")
            self._records[request_id] = record
        self._mutate(mutation)
        return record

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        handle = self._lock_file()
        try:
            self._load_unlocked()
            return tuple(self._records[key] for key in sorted(self._records))
        finally:
            self._unlock_file(handle)
