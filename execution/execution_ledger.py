from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from core.file_lock import exclusive_file_lock


class ExecutionLedgerStatus(str, Enum):
    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED_EXECUTED = "RECONCILED_EXECUTED"
    RECONCILED_NOT_EXECUTED = "RECONCILED_NOT_EXECUTED"


class ExecutionLedger:
    """Persistent request state and reconciliation evidence for execution idempotency."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._states: dict[str, ExecutionLedgerStatus] = {}
        self._reconciliation_evidence: dict[str, dict[str, str]] = {}
        with self._process_lock():
            self._load()

    def _process_lock(self):
        return exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock"))

    def _load(self) -> None:
        if not self.path.exists():
            self._states = {}
            self._reconciliation_evidence = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states, self._reconciliation_evidence = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> tuple[dict[str, ExecutionLedgerStatus], dict[str, dict[str, str]]]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return ({item: ExecutionLedgerStatus.ACCEPTED for item in payload}, {})
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")

        envelope_keys = set(payload).issubset({"states", "reconciliation_evidence"}) and "states" in payload
        if not envelope_keys:
            states_payload = payload
            evidence_payload: object = {}
        else:
            states_payload = payload.get("states")
            evidence_payload = payload.get("reconciliation_evidence", {})
            if not isinstance(states_payload, dict) or not isinstance(evidence_payload, dict):
                raise ValueError("ledger de execução inválido.")

        states: dict[str, ExecutionLedgerStatus] = {}
        for request_id, raw_status in states_payload.items():
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("ledger de execução inválido.")
            try:
                states[request_id] = ExecutionLedgerStatus(raw_status)
            except ValueError as exc:
                raise ValueError("ledger de execução inválido.") from exc

        evidence: dict[str, dict[str, str]] = {}
        for request_id, raw_evidence in evidence_payload.items():
            if request_id not in states or not isinstance(raw_evidence, dict):
                raise ValueError("ledger de execução inválido.")
            if states[request_id] not in (
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ):
                raise ValueError("ledger de execução inválido.")
            evidence_id = raw_evidence.get("evidence_id")
            evidence_source = raw_evidence.get("evidence_source")
            if (
                not isinstance(evidence_id, str)
                or not evidence_id.strip()
                or not isinstance(evidence_source, str)
                or not evidence_source.strip()
            ):
                raise ValueError("ledger de execução inválido.")
            evidence[request_id] = {
                "evidence_id": evidence_id,
                "evidence_source": evidence_source,
            }
        return states, evidence

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload: dict[str, Any] = {
            "states": {key: self._states[key].value for key in sorted(self._states)},
            "reconciliation_evidence": {
                key: self._reconciliation_evidence[key]
                for key in sorted(self._reconciliation_evidence)
            },
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def _mutate_locked(self, mutation) -> None:
        """Serialize read/modify/write so two processes cannot reserve the same ID."""
        with self._process_lock():
            self._load()
            mutation()
            self._write()

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        self._validate_id(request_id)
        with self._process_lock():
            self._load()
            return self._states.get(request_id)

    def contains(self, request_id: str) -> bool:
        return self.status(request_id) is not None

    def reconciliation_evidence(self, request_id: str) -> dict[str, str] | None:
        self._validate_id(request_id)
        with self._process_lock():
            self._load()
            evidence = self._reconciliation_evidence.get(request_id)
            return dict(evidence) if evidence is not None else None

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

    def reconcile(
        self,
        request_id: str,
        *,
        executed: bool,
        evidence_id: str | None = None,
        evidence_source: str | None = None,
    ) -> None:
        self._validate_id(request_id)
        if (evidence_id is None) != (evidence_source is None):
            raise ValueError("evidence_id e evidence_source devem ser fornecidos juntos")
        if evidence_id is not None:
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                raise ValueError("evidence_id não pode ser vazio")
            if not isinstance(evidence_source, str) or not evidence_source.strip():
                raise ValueError("evidence_source não pode ser vazio")

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
            if evidence_id is not None and evidence_source is not None:
                self._reconciliation_evidence[request_id] = {
                    "evidence_id": evidence_id,
                    "evidence_source": evidence_source,
                }

        self._mutate_locked(mutation)

    def records(self) -> tuple[str, ...]:
        with self._process_lock():
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
