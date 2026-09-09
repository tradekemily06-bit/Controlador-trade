from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


class ExecutionLedgerStatus(str, Enum):
    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED_EXECUTED = "RECONCILED_EXECUTED"
    RECONCILED_NOT_EXECUTED = "RECONCILED_NOT_EXECUTED"


class ExecutionLedger:
    """Persistent request state for restart-safe REAL execution idempotency."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._states: dict[str, ExecutionLedgerStatus] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> dict[str, ExecutionLedgerStatus]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return {item: ExecutionLedgerStatus.ACCEPTED for item in payload}
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")
        states: dict[str, ExecutionLedgerStatus] = {}
        for request_id, raw_status in payload.items():
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("ledger de execução inválido.")
            try:
                states[request_id] = ExecutionLedgerStatus(raw_status)
            except ValueError as exc:
                raise ValueError("ledger de execução inválido.") from exc
        return states

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {key: self._states[key].value for key in sorted(self._states)}
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def _mutate_locked(self, mutation) -> None:
        """Serialize read/modify/write so two processes cannot reserve the same ID."""
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                self._load()
                mutation()
                self._write()
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        self._validate_id(request_id)
        self._load()
        return self._states.get(request_id)

    def contains(self, request_id: str) -> bool:
        return self.status(request_id) is not None

    def reserve(self, request_id: str) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            if request_id in self._states:
                raise ValueError("request_id já possui estado; replay REAL recusado.")
            self._states[request_id] = ExecutionLedgerStatus.RESERVED

        self._mutate_locked(mutation)

    def record(self, request_id: str) -> None:
        """Backward-compatible terminal record for existing DEMO infrastructure."""
        self._validate_id(request_id)

        def mutation() -> None:
            if request_id not in self._states:
                self._states[request_id] = ExecutionLedgerStatus.ACCEPTED

        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.ACCEPTED)

    def mark_rejected(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.UNKNOWN)

    def reconcile(self, request_id: str, *, executed: bool) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            if self._states.get(request_id) not in (
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
            ):
                raise ValueError("request_id não está em estado incerto reconciliável.")
            self._states[request_id] = (
                ExecutionLedgerStatus.RECONCILED_EXECUTED
                if executed
                else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
            )

        self._mutate_locked(mutation)

    def records(self) -> tuple[str, ...]:
        self._load()
        return tuple(sorted(self._states))

    @staticmethod
    def _validate_id(request_id: str) -> None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")

    def _transition(self, request_id: str, status: ExecutionLedgerStatus) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado.")
            if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                raise ValueError(f"transição inválida de {current.value} para {status.value}.")
            self._states[request_id] = status

        self._mutate_locked(mutation)
