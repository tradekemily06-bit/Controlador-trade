from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime

from core.runtime_checkpoint import process_file_lock


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
    """Durable lifecycle store with enforced transitions and atomic persistence."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, ExecutionLifecycleRecord] = {}
        self._load()

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
    def _transition_allowed(
        previous: ExecutionLifecycleState | None,
        current: ExecutionLifecycleState,
    ) -> bool:
        if previous is None:
            return current in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN)
        if previous is ExecutionLifecycleState.PENDING:
            return current in (
                ExecutionLifecycleState.ACCEPTED,
                ExecutionLifecycleState.REJECTED,
                ExecutionLifecycleState.UNKNOWN,
            )
        return current is previous

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
                    item["request_id"],
                    ExecutionLifecycleState(item["state"]),
                    datetime.fromisoformat(item["updated_at"]),
                    item.get("message", ""),
                )
                self._validate(record)
                previous = loaded.get(record.request_id)
                if previous is not None:
                    raise ValueError("ciclo de execução persistido inválido: request_id duplicado.")
                if previous is not None and not self._transition_allowed(
                    previous.state, record.state
                ):
                    raise ValueError("histórico de ciclo contém transição inválida.")
                loaded[record.request_id] = record
            self._records = loaded
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    def _mutate_locked(self, mutation) -> None:
        """Serialize lifecycle read/modify/write across processes."""
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with process_file_lock(lock_path):
            self._load()
            mutation()
            self._save()

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)

        def mutation() -> None:
            previous = self._records.get(record.request_id)
            if not self._transition_allowed(
                previous.state if previous else None, record.state
            ):
                raise ValueError(
                    "transição de ciclo inválida: "
                    f"{previous.state.value if previous else 'NONE'} -> {record.state.value}"
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

        result: ExecutionLifecycleRecord | None = None

        def mutation() -> None:
            nonlocal result
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state not in (
                ExecutionLifecycleState.UNKNOWN,
                ExecutionLifecycleState.PENDING,
            ):
                raise ValueError("somente UNKNOWN/PENDING pode ser reconciliado.")
            record = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._validate(record)
            self._records[request_id] = record
            result = record

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def reconcile_missing(
        self,
        request_id: str,
        state: ExecutionLifecycleState,
        *,
        updated_at: datetime,
        message: str = "",
    ) -> ExecutionLifecycleRecord:
        """Create terminal lifecycle evidence for a Ledger-only orphan after explicit reconciliation."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação de órfão exige estado ACCEPTED ou REJECTED.")
        result: ExecutionLifecycleRecord | None = None

        def mutation() -> None:
            nonlocal result
            if request_id in self._records:
                raise ValueError("Lifecycle já possui registro para request_id.")
            record = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._validate(record)
            self._records[request_id] = record
            result = record

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        self._load()
        return tuple(self._records[k] for k in sorted(self._records))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = json.dumps(
            [
                {
                    "request_id": record.request_id,
                    "state": record.state.value,
                    "updated_at": record.updated_at.isoformat(),
                    "message": record.message,
                }
                for record in (self._records[k] for k in sorted(self._records))
            ],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        if os.name != "nt":
            with self.path.open("rb") as handle:
                os.fsync(handle.fileno())
        try:
            fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
