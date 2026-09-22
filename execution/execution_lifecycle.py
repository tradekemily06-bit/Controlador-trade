from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
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
    """Durable execution state with atomic, cross-process serialized writes."""

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

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)

        def mutation() -> None:
            previous = self._records.get(record.request_id)
            if previous is not None:
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
                if record.state not in allowed[previous.state]:
                    if previous.state is ExecutionLifecycleState.UNKNOWN:
                        raise ValueError("execução UNKNOWN requer reconciliação explícita.")
                    raise ValueError(
                        f"transição de lifecycle inválida: {previous.state.value} -> {record.state.value}."
                    )
            self._records[record.request_id] = record

        self._mutate_locked(mutation)

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        self._load()
        return self._records.get(request_id)

    def project_terminal(
        self,
        request_id: str,
        state: ExecutionLifecycleState,
        *,
        updated_at: datetime,
        message: str = "",
    ) -> ExecutionLifecycleRecord:
        """Repair the local lifecycle projection from an already-terminal authoritative Ledger state."""
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("projeção terminal exige ACCEPTED ou REJECTED.")
        self._validate(ExecutionLifecycleRecord(request_id, state, updated_at, message))

        def mutation() -> None:
            current = self._records.get(request_id)
            if current is None:
                self._records[request_id] = ExecutionLifecycleRecord(request_id, state, updated_at, message)
                return
            if current.state in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
                if current.state is not state:
                    raise ValueError("projeção terminal conflita com lifecycle terminal existente.")
                return
            if current.state not in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN):
                raise ValueError("projeção terminal em estado inválido.")

            self._records[request_id] = ExecutionLifecycleRecord(request_id, state, updated_at, message)

        self._mutate_locked(mutation)
        return self._records[request_id]

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
        if not isinstance(updated_at, datetime):
            raise ValueError("timestamp inválido.")
        if not isinstance(message, str):
            raise ValueError("mensagem inválida.")
        self._validate(
            ExecutionLifecycleRecord(request_id, state, updated_at, message)
        )

        def mutation() -> None:
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state not in (
                ExecutionLifecycleState.PENDING,
                ExecutionLifecycleState.UNKNOWN,
            ):
                raise ValueError("reconciliação só pode resolver PENDING/UNKNOWN.")
            self._records[request_id] = ExecutionLifecycleRecord(
                request_id, state, updated_at, message
            )

        self._mutate_locked(mutation)
        return self._records[request_id]

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))

    def _mutate_locked(self, mutation) -> None:
        """Serialize read/modify/write across processes and replace atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with lock_path.open("a+b") as lock_file:
            self._acquire_lock(lock_file)
            try:
                self._load()
                mutation()
                self._save()
            finally:
                self._release_lock(lock_file)

    def _fsync_directory(self) -> None:
        if os.name != "posix":
            return
        directory_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _acquire_lock(lock_file) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            return
        if msvcrt is not None:
            lock_file.seek(0)
            lock_file.write(b"0")
            lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            return
        raise OSError("nenhum mecanismo de lock suportado neste sistema")

    @staticmethod
    def _release_lock(lock_file) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            return
        if msvcrt is not None:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            return
        raise OSError("nenhum mecanismo de lock suportado neste sistema")

    def _save(self) -> None:
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
                    for r in sorted(self._records.values(), key=lambda item: item.request_id)
                ],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        with temporary.open("rb+") as temp_file:
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temporary, self.path)
        self._fsync_directory()
