from __future__ import annotations

import json
import os
import tempfile
from enum import Enum
from pathlib import Path

from core.request_identity import REQUEST_ID_PATTERN, validate_request_id

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
        self._external_bindings: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states, self._external_bindings = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> tuple[dict[str, ExecutionLedgerStatus], dict[str, str]]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not REQUEST_ID_PATTERN.fullmatch(item) for item in payload):
                raise ValueError("ledger de execução inválido.")
            return {item: ExecutionLedgerStatus.ACCEPTED for item in payload}, {}
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")
        raw_states = payload.get("states", payload)
        raw_bindings = payload.get("external_bindings", {})
        if not isinstance(raw_states, dict) or not isinstance(raw_bindings, dict):
            raise ValueError("ledger de execução inválido.")
        states: dict[str, ExecutionLedgerStatus] = {}
        for request_id, raw_status in raw_states.items():
            if not isinstance(request_id, str) or not REQUEST_ID_PATTERN.fullmatch(request_id):
                raise ValueError("ledger de execução inválido.")
            try:
                states[request_id] = ExecutionLedgerStatus(raw_status)
            except ValueError as exc:
                raise ValueError("ledger de execução inválido.") from exc
        bindings: dict[str, str] = {}
        for binding_key, request_id in raw_bindings.items():
            if not isinstance(binding_key, str) or not binding_key.strip():
                raise ValueError("binding externo inválido.")
            if not isinstance(request_id, str) or not request_id.strip() or request_id not in states:
                raise ValueError("binding externo inválido.")
            bindings[binding_key] = request_id
        return states, bindings

    @staticmethod
    def _binding_key(broker: str, adapter: str, external_id: str) -> str:
        if not all(isinstance(value, str) and value.strip() for value in (broker, adapter, external_id)):
            raise ValueError("identidade externa inválida.")
        return json.dumps([broker.strip().casefold(), adapter.strip().casefold(), external_id.strip()], ensure_ascii=False, separators=(",", ":"))

    def external_binding(self, *, broker: str, adapter: str, external_id: str) -> str | None:
        key = self._binding_key(broker, adapter, external_id)
        self._load()
        return self._external_bindings.get(key)

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {"states": {key: self._states[key].value for key in sorted(self._states)}, "external_bindings": {key: self._external_bindings[key] for key in sorted(self._external_bindings)}}
        fd, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise

    def _mutate_locked(self, mutation) -> None:
        """Serialize read/modify/write so two processes cannot reserve the same ID."""
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

    def mark_accepted(self, request_id: str, *, broker: str, adapter: str, external_id: str) -> None:
        self._validate_id(request_id)
        key = self._binding_key(broker, adapter, external_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                raise ValueError("request_id não está em estado aceito para confirmação.")
            owner = self._external_bindings.get(key)
            if owner is not None and owner != request_id:
                raise ValueError("external order identity já está vinculada a outro request_id.")
            self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
            self._external_bindings[key] = request_id

        self._mutate_locked(mutation)

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
        validate_request_id(request_id)

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
