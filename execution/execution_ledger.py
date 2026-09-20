from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

from core.file_lock import exclusive_file_lock


class ExecutionLedgerStatus(str, Enum):
    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED_EXECUTED = "RECONCILED_EXECUTED"
    RECONCILED_NOT_EXECUTED = "RECONCILED_NOT_EXECUTED"


class ExecutionLedger:
    """Persistent request state plus durable external identity for REAL idempotency."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._states: dict[str, ExecutionLedgerStatus] = {}
        self._external_ids: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states, self._external_ids = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> tuple[dict[str, ExecutionLedgerStatus], dict[str, str]]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return ({item: ExecutionLedgerStatus.ACCEPTED for item in payload}, {})

        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")

        # Backward compatibility with the former {request_id: status} format.
        if "states" not in payload:
            states_raw = payload
            external_raw: object = {}
        else:
            states_raw = payload.get("states")
            external_raw = payload.get("external_ids", {})
            if not isinstance(states_raw, dict) or not isinstance(external_raw, dict):
                raise ValueError("ledger de execução inválido.")

        states: dict[str, ExecutionLedgerStatus] = {}
        for request_id, raw_status in states_raw.items():
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("ledger de execução inválido.")
            try:
                states[request_id] = ExecutionLedgerStatus(raw_status)
            except ValueError as exc:
                raise ValueError("ledger de execução inválido.") from exc

        external_ids: dict[str, str] = {}
        for request_id, external_id in external_raw.items():
            if request_id not in states:
                raise ValueError("external_id referencia request_id ausente.")
            if not isinstance(external_id, str) or not external_id.strip():
                raise ValueError("external_id persistido inválido.")
            external_ids[request_id] = external_id.strip()

        if len(external_ids) != len(set(external_ids.values())):
            raise ValueError("external_id duplicado no ledger de execução.")

        for request_id, external_id in external_ids.items():
            if states[request_id] not in (
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
            ):
                raise ValueError("external_id associado a estado incompatível.")

        return states, external_ids

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {
            "states": {key: self._states[key].value for key in sorted(self._states)},
            "external_ids": {key: self._external_ids[key] for key in sorted(self._external_ids)},
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    def _mutate_locked(self, mutation) -> None:
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with exclusive_file_lock(lock_path):
            self._load()
            mutation()
            self._write()

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        self._validate_id(request_id)
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with exclusive_file_lock(lock_path):
            self._load()
            return self._states.get(request_id)

    def external_id(self, request_id: str) -> str | None:
        self._validate_id(request_id)
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with exclusive_file_lock(lock_path):
            self._load()
            return self._external_ids.get(request_id)

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
            current = self._states.get(request_id)
            if current is None:
                self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
            elif current is ExecutionLedgerStatus.RESERVED:
                # DEMO/PAPER path: reserve before dispatch, then terminalize
                # locally without requiring a broker external_id.
                self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
            else:
                raise ValueError(f"transição DEMO inválida de {current.value} para ACCEPTED.")

        self._mutate_locked(mutation)

    def bind_external_id(self, request_id: str, external_id: str) -> None:
        """Durably bind broker identity before terminalizing a REAL result."""
        self._validate_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                raise ValueError("external_id só pode ser vinculado a uma execução incerta/reservada.")
            self._bind_external_id(request_id, external_id)

        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str, *, external_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.ACCEPTED, external_id=external_id)

    def mark_rejected(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str, *, external_id: str | None = None) -> None:
        self._transition(request_id, ExecutionLedgerStatus.UNKNOWN, external_id=external_id)

    def reconcile(self, request_id: str, *, executed: bool, external_id: str | None = None) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            if self._states.get(request_id) not in (
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
            ):
                raise ValueError("request_id não está em estado incerto reconciliável.")
            if executed and (not isinstance(external_id, str) or not external_id.strip()):
                raise ValueError("execução reconciliada exige external_id.")
            if not executed and external_id is not None:
                raise ValueError("reconciliação NOT_EXECUTED não pode associar external_id.")
            if external_id is not None:
                self._bind_external_id(request_id, external_id)
            self._states[request_id] = (
                ExecutionLedgerStatus.RECONCILED_EXECUTED
                if executed
                else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
            )

        self._mutate_locked(mutation)

    def snapshot(self) -> dict[str, ExecutionLedgerStatus]:
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with exclusive_file_lock(lock_path):
            self._load()
            return dict(self._states)

    def records(self) -> tuple[str, ...]:
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with exclusive_file_lock(lock_path):
            self._load()
            return tuple(sorted(self._states))

    @staticmethod
    def _validate_id(request_id: str) -> None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")

    def _bind_external_id(self, request_id: str, external_id: str) -> None:
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido.")
        normalized = external_id.strip()
        existing = self._external_ids.get(request_id)
        if existing is not None and existing != normalized:
            raise ValueError("request_id já possui external_id diferente.")
        owner = next((rid for rid, eid in self._external_ids.items() if eid == normalized and rid != request_id), None)
        if owner is not None:
            raise ValueError("external_id já está associado a outro request_id.")
        self._external_ids[request_id] = normalized

    def _transition(self, request_id: str, status: ExecutionLedgerStatus, *, external_id: str | None = None) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado.")
            if current is not ExecutionLedgerStatus.RESERVED:
                raise ValueError(
                    f"transição inválida de {current.value} para {status.value}; UNKNOWN exige reconciliação explícita."
                    if current is ExecutionLedgerStatus.UNKNOWN
                    else f"transição inválida de {current.value} para {status.value}."
                )
            if status is ExecutionLedgerStatus.ACCEPTED:
                self._bind_external_id(request_id, external_id or "")
            elif external_id is not None:
                self._bind_external_id(request_id, external_id)
            self._states[request_id] = status

        self._mutate_locked(mutation)
