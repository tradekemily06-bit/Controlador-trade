from __future__ import annotations

import json
import os
import uuid
from enum import Enum
from pathlib import Path

from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus

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
        self._external_ids: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._states = {}
            self._external_ids = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states, self._external_ids = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> tuple[dict[str, ExecutionLedgerStatus], dict[str, str]]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 128 for item in payload):
                raise ValueError("ledger de execução inválido.")
            if len(set(payload)) != len(payload):
                raise ValueError("ledger de execução inválido.")
            return ({item: ExecutionLedgerStatus.ACCEPTED for item in payload}, {})
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")
        states: dict[str, ExecutionLedgerStatus] = {}
        external_ids: dict[str, str] = {}
        for request_id, raw_status in payload.items():
            if not isinstance(request_id, str) or not request_id.strip() or len(request_id.strip()) > 128:
                raise ValueError("ledger de execução inválido.")
            if isinstance(raw_status, dict):
                status_value = raw_status.get("status")
                external_id = raw_status.get("external_id")
                if external_id is not None and (not isinstance(external_id, str) or not external_id.strip() or len(external_id.strip()) > 256):
                    raise ValueError("ledger de execução inválido.")
            else:
                status_value = raw_status
                external_id = None
            try:
                states[request_id] = ExecutionLedgerStatus(status_value)
            except ValueError as exc:
                raise ValueError("ledger de execução inválido.") from exc
            if external_id is not None:
                external_ids[request_id] = external_id.strip()
        return states, external_ids

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        payload = {key: ({"status": self._states[key].value, "external_id": self._external_ids[key]} if key in self._external_ids else self._states[key].value) for key in sorted(self._states)}
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

    def reserve_exclusive(self, request_id: str) -> None:
        """Atomically reserve a REAL request only when no other request is uncertain."""
        self._validate_id(request_id)

        def mutation() -> None:
            if request_id in self._states:
                raise ValueError("request_id já possui estado; replay REAL recusado.")
            uncertain = tuple(
                rid
                for rid, status in self._states.items()
                if rid != request_id
                and status in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN)
            )
            if uncertain:
                raise ValueError("há outra execução REAL em estado incerto.")
            self._states[request_id] = ExecutionLedgerStatus.RESERVED

        self._mutate_locked(mutation)

    def record(self, request_id: str) -> None:
        """Backward-compatible terminal record for existing DEMO infrastructure."""
        self._validate_id(request_id)

        def mutation() -> None:
            if request_id not in self._states:
                self._states[request_id] = ExecutionLedgerStatus.ACCEPTED

        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str, external_id: str) -> None:
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip() or len(external_id.strip()) > 256:
            raise ValueError("external_id obrigatório e inválido.")

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is not ExecutionLedgerStatus.RESERVED:
                raise ValueError("transição inválida para ACCEPTED.")
            normalized_external_id = external_id.strip()
            owner = next(
                (rid for rid, eid in self._external_ids.items() if eid == normalized_external_id and rid != request_id),
                None,
            )
            if owner is not None:
                raise ValueError("external_id já associado a outro request_id.")
            self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
            self._external_ids[request_id] = normalized_external_id
        self._mutate_locked(mutation)

    def external_id(self, request_id: str) -> str | None:
        self._validate_id(request_id)
        self._load()
        return self._external_ids.get(request_id)

    def mark_rejected(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.UNKNOWN)

    def reconcile_observation(self, request_id: str, observation: ExternalOrderObservation) -> None:
        self._validate_id(request_id)
        if not isinstance(observation, ExternalOrderObservation):
            raise ValueError("observação externa inválida.")
        if observation.request_id != request_id:
            raise ValueError("request_id da observação difere da requisição.")
        if observation.status not in (ExternalOrderStatus.EXECUTED, ExternalOrderStatus.NOT_EXECUTED):
            raise ValueError("observação externa não é terminal.")
        if observation.external_id is not None and (
            not isinstance(observation.external_id, str)
            or not observation.external_id.strip()
            or len(observation.external_id.strip()) > 256
        ):
            raise ValueError("external_id da observação inválido.")

        def mutation() -> None:
            current = self._states.get(request_id)
            if current not in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                raise ValueError("request_id não está em estado incerto reconciliável.")

            stored_external_id = self._external_ids.get(request_id)
            observed_external_id = observation.external_id.strip() if observation.external_id else None
            if stored_external_id is not None and observed_external_id != stored_external_id:
                raise ValueError("external_id da observação difere do identificador persistido.")
            if observed_external_id is not None and stored_external_id is None:
                owner = next(
                    (rid for rid, eid in self._external_ids.items() if eid == observed_external_id and rid != request_id),
                    None,
                )
                if owner is not None:
                    raise ValueError("external_id já associado a outro request_id.")
                self._external_ids[request_id] = observed_external_id

            self._states[request_id] = (
                ExecutionLedgerStatus.RECONCILED_EXECUTED
                if observation.status is ExternalOrderStatus.EXECUTED
                else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
            )

        self._mutate_locked(mutation)

    def records(self) -> tuple[str, ...]:
        self._load()
        return tuple(sorted(self._states))

    def uncertain_request_ids(self) -> tuple[str, ...]:
        self._load()
        return tuple(sorted(
            request_id
            for request_id, status in self._states.items()
            if status in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN)
        ))

    @staticmethod
    def _validate_id(request_id: str) -> None:
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id.strip()) > 128:
            raise ValueError("request_id inválido.")

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
