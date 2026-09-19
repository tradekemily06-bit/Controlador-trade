from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime

from core.request_identity import REQUEST_ID_PATTERN, validate_request_id

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


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
    """Durable execution state; writes are serialized and atomic."""

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
                if record.request_id in records:
                    raise ValueError("request_id duplicado no lifecycle.")
                records[record.request_id] = record
            self._records = records
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    @staticmethod
    def _validate(record: ExecutionLifecycleRecord) -> None:
        validate_request_id(record.request_id)
        if not isinstance(record.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if not isinstance(record.updated_at, datetime) or record.updated_at.tzinfo is None or record.updated_at.utcoffset() is None:
            raise ValueError("timestamp deve ser timezone-aware.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem inválida.")

    def _mutate_locked(self, mutation):
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        lock_fd = os.open(lock_path, flags, 0o600)
        with os.fdopen(lock_fd, "a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                self._load()
                mutation()
                self._save()
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)

        def mutation() -> None:
            previous = self._records.get(record.request_id)
            if previous is None:
                if record.state not in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN):
                    raise ValueError("execução nova deve iniciar em PENDING ou UNKNOWN.")
            elif previous.state is ExecutionLifecycleState.UNKNOWN:
                if record.state is not ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("execução UNKNOWN requer reconciliação explícita.")
            elif previous.state is ExecutionLifecycleState.PENDING:
                if record.state is ExecutionLifecycleState.PENDING:
                    raise ValueError("execução PENDING já existe; reserva duplicada recusada.")
                if record.state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED, ExecutionLifecycleState.UNKNOWN):
                    raise ValueError("transição de PENDING inválida.")
            else:
                raise ValueError("estado terminal não pode ser sobrescrito.")
            self._records[record.request_id] = record

        self._mutate_locked(mutation)

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        validate_request_id(request_id)
        self._load()
        return self._records.get(request_id)

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        self._validate(ExecutionLifecycleRecord(request_id, state, updated_at, message))

        def mutation() -> None:
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state is not ExecutionLifecycleState.UNKNOWN:
                raise ValueError("somente UNKNOWN pode ser reconciliado explicitamente.")
            self._records[request_id] = ExecutionLifecycleRecord(request_id, state, updated_at, message)

        self._mutate_locked(mutation)
        return self.get(request_id)  # type: ignore[return-value]

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        records = [self._records[key] for key in sorted(self._records)]
        payload = json.dumps([{"request_id": r.request_id, "state": r.state.value, "updated_at": r.updated_at.isoformat(), "message": r.message} for r in records], ensure_ascii=False, indent=2, sort_keys=True)
        fd, temporary_name = tempfile.mkstemp(prefix="." + self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise
