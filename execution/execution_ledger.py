from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None


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
        self._external_ids: dict[str, str] = {}
        self._external_reference_required: dict[str, bool] = {}
        self._brokers: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states, self._external_ids, self._external_reference_required = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> tuple[dict[str, ExecutionLedgerStatus], dict[str, str], dict[str, bool], dict[str, str]]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return ({item: ExecutionLedgerStatus.ACCEPTED for item in payload}, {}, {})
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")
        states: dict[str, ExecutionLedgerStatus] = {}
        external_ids: dict[str, str] = {}
        external_reference_required: dict[str, bool] = {}
        brokers: dict[str, str] = {}
        for request_id, raw_status in payload.items():
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("ledger de execução inválido.")
            if isinstance(raw_status, dict):
                status_value = raw_status.get("status")
                external_id = raw_status.get("external_id")
                external_required = raw_status.get("external_id_required")
                broker_id = raw_status.get("broker_id")
                if broker_id is not None and (not isinstance(broker_id, str) or not broker_id.strip()):
                    raise ValueError("ledger de execução inválido.")
                if external_required is not None and not isinstance(external_required, bool):
                    raise ValueError("ledger de execução inválido.")
                if external_id is not None and (not isinstance(external_id, str) or not external_id.strip()):
                    raise ValueError("ledger de execução inválido.")
            else:
                status_value = raw_status
                external_id = None
                external_required = None
                broker_id = None
            try:
                states[request_id] = ExecutionLedgerStatus(status_value)
            except ValueError as exc:
                raise ValueError("ledger de execução inválido.") from exc
            if external_id is not None:
                external_ids[request_id] = external_id.strip()
            if external_required is not None:
                external_reference_required[request_id] = external_required
            if broker_id is not None:
                brokers[request_id] = broker_id.strip()
        return states, external_ids, external_reference_required, brokers

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {
            key: (
                {"status": self._states[key].value, "external_id": self._external_ids[key], "external_id_required": self._external_reference_required.get(key, True), **({"broker_id": self._brokers[key]} if key in self._brokers else {})}
                if key in self._external_ids
                else (
                    {"status": self._states[key].value, "external_id_required": self._external_reference_required[key], **({"broker_id": self._brokers[key]} if key in self._brokers else {})}
                    if key in self._external_reference_required
                    else self._states[key].value
                )
            )
            for key in sorted(self._states)
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with temporary.open("rb+") as temp_file:
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temporary, self.path)
        self._fsync_directory()

    def _fsync_directory(self) -> None:
        if os.name != "posix":
            return
        directory_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _mutate_locked(self, mutation) -> None:
        """Serialize read/modify/write so two processes cannot reserve the same ID."""
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            self._acquire_lock(lock_file)
            try:
                self._load()
                mutation()
                self._write()
            finally:
                self._release_lock(lock_file)

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

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        self._validate_id(request_id)
        self._load()
        return self._states.get(request_id)

    def contains(self, request_id: str) -> bool:
        return self.status(request_id) is not None

    def reserve(self, request_id: str, broker_id: str | None = None) -> None:
        self._validate_id(request_id)
        if broker_id is not None and (not isinstance(broker_id, str) or not broker_id.strip()):
            raise ValueError("broker_id inválido.")

        def mutation() -> None:
            if request_id in self._states:
                raise ValueError("request_id já possui estado; replay REAL recusado.")
            self._states[request_id] = ExecutionLedgerStatus.RESERVED
            if broker_id is not None:
                self._brokers[request_id] = broker_id.strip()

        self._mutate_locked(mutation)

    def record(self, request_id: str) -> None:
        """Backward-compatible terminal record for existing DEMO infrastructure."""
        self._validate_id(request_id)

        def mutation() -> None:
            if request_id not in self._states:
                self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
                self._external_reference_required[request_id] = False

        self._mutate_locked(mutation)

    def mark_demo_accepted(self, request_id: str) -> None:
        """Persist a terminal DEMO acceptance without requiring a broker external_id."""
        self._validate_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                raise ValueError("transição DEMO para ACCEPTED inválida.")
            self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
            self._external_reference_required[request_id] = False

        self._mutate_locked(mutation)

    def attach_external_id(self, request_id: str, external_id: str) -> None:
        """Durably bind the broker reference before terminal ACCEPTED persistence."""
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id é obrigatório.")

        def mutation() -> None:
            current = self._states.get(request_id)
            if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                raise ValueError("external_id só pode ser anexado a estado incerto.")
            normalized = external_id.strip()
            existing = self._external_ids.get(request_id)
            if existing is not None and existing != normalized:
                raise ValueError("request_id já possui outro external_id.")
            owner = next((rid for rid, eid in self._external_ids.items() if eid == normalized and rid != request_id), None)
            if owner is not None:
                raise ValueError("external_id já está associado a outro request_id.")
            self._external_ids[request_id] = normalized

        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str, *, external_id: str) -> None:
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id é obrigatório para aceite REAL.")

        def mutation() -> None:
            current = self._states.get(request_id)
            if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                raise ValueError("transição para ACCEPTED inválida.")
            normalized = external_id.strip()
            existing = self._external_ids.get(request_id)
            if existing is not None and existing != normalized:
                raise ValueError("request_id já possui outro external_id.")
            owner = next((rid for rid, eid in self._external_ids.items() if eid == normalized and rid != request_id), None)
            if owner is not None:
                raise ValueError("external_id já está associado a outro request_id.")
            self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
            self._external_ids[request_id] = normalized
            self._external_reference_required[request_id] = True

        self._mutate_locked(mutation)

    def mark_rejected(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.UNKNOWN)

    def reconcile(self, request_id: str, *, executed: bool, external_id: str) -> None:
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("reconciliação exige external_id durável.")

        def mutation() -> None:
            if self._states.get(request_id) not in (
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
            ):
                raise ValueError("request_id não está em estado incerto reconciliável.")
            normalized = external_id.strip()
            stored = self._external_ids.get(request_id)
            if stored != normalized:
                raise ValueError("external_id da reconciliação difere do external_id durável.")
            self._states[request_id] = (
                ExecutionLedgerStatus.RECONCILED_EXECUTED
                if executed
                else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
            )
            self._external_reference_required[request_id] = True

        self._mutate_locked(mutation)

    def broker_id(self, request_id: str) -> str | None:
        self._validate_id(request_id)
        self._load()
        return self._brokers.get(request_id)

    def external_reference_required(self, request_id: str) -> bool:
        self._validate_id(request_id)
        self._load()
        return self._external_reference_required.get(request_id, False)

    def external_id(self, request_id: str) -> str | None:
        self._validate_id(request_id)
        self._load()
        return self._external_ids.get(request_id)

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
