from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
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
    """Durable execution state with cross-process mutation serialization."""

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

    def _lock_path(self) -> Path:
        return self.path.with_name(f".{self.path.name}.lock")

    def _with_lock(self):
        return self._lock_path().open("a+b")

    @staticmethod
    def _lock(lock_file) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            return
        if msvcrt is not None:
            lock_file.seek(0)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)

    @staticmethod
    def _unlock(lock_file) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)

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

    def _mutate_locked(self, mutation) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._with_lock() as lock_file:
            self._lock(lock_file)
            try:
                self._load()
                mutation()
                self._save()
            finally:
                self._unlock(lock_file)

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)

        def mutation() -> None:
            previous = self._records.get(record.request_id)
            if previous is None:
                if record.state is not ExecutionLifecycleState.PENDING:
                    raise ValueError("novo ciclo deve iniciar em PENDING.")
            elif previous.state is ExecutionLifecycleState.UNKNOWN:
                if record.state is not ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("execução UNKNOWN requer reconciliação explícita.")
            elif previous.state in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
                raise ValueError("estado terminal não pode ser alterado.")
            elif previous.state is ExecutionLifecycleState.PENDING and record.state not in (
                ExecutionLifecycleState.PENDING,
                ExecutionLifecycleState.ACCEPTED,
                ExecutionLifecycleState.REJECTED,
                ExecutionLifecycleState.UNKNOWN,
            ):
                raise ValueError("transição de PENDING inválida.")
            self._records[record.request_id] = record

        self._mutate_locked(mutation)

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        self._load()
        return self._records.get(request_id)

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        if not isinstance(updated_at, datetime):
            raise ValueError("timestamp inválido.")

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
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))
