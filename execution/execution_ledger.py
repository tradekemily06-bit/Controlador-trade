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
    """Persistent request state, REAL identity and reconciliation evidence."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path).resolve()
        self._states: dict[str, ExecutionLedgerStatus] = {}
        self._reconciliation_evidence: dict[str, dict[str, str]] = {}
        self._execution_context: dict[str, dict[str, str | None]] = {}
        with self._process_lock():
            self._load()

    def _process_lock(self):
        return exclusive_file_lock(self.path.with_name(f".{self.path.name}.lock"))

    def _load(self) -> None:
        if not self.path.exists():
            self._states = {}
            self._reconciliation_evidence = {}
            self._execution_context = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states, self._reconciliation_evidence, self._execution_context = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> tuple[dict[str, ExecutionLedgerStatus], dict[str, dict[str, str]], dict[str, dict[str, str | None]]]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return ({item: ExecutionLedgerStatus.ACCEPTED for item in payload}, {}, {})
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")

        envelope_keys = set(payload).issubset({"states", "reconciliation_evidence", "execution_context"}) and "states" in payload
        if not envelope_keys:
            states_payload = payload
            evidence_payload: object = {}
            context_payload: object = {}
        else:
            states_payload = payload.get("states")
            evidence_payload = payload.get("reconciliation_evidence", {})
            context_payload = payload.get("execution_context", {})
            if not isinstance(states_payload, dict) or not isinstance(evidence_payload, dict) or not isinstance(context_payload, dict):
                raise ValueError("ledger de execução inválido.")

        states: dict[str, ExecutionLedgerStatus] = {}
        for request_id, raw_status in states_payload.items():
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("ledger de execução inválido.")
            if request_id in states:
                raise ValueError("ledger de execução inválido: request_id duplicado.")
            try:
                states[request_id] = ExecutionLedgerStatus(raw_status)
            except ValueError as exc:
                raise ValueError("ledger de execução inválido.") from exc

        evidence: dict[str, dict[str, str]] = {}
        seen_evidence_ids: set[str] = set()
        for request_id, raw_evidence in evidence_payload.items():
            if request_id not in states or not isinstance(raw_evidence, dict):
                raise ValueError("ledger de execução inválido.")
            if states[request_id] not in (ExecutionLedgerStatus.RECONCILED_EXECUTED, ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED):
                raise ValueError("ledger de execução inválido.")
            evidence_id = raw_evidence.get("evidence_id")
            evidence_source = raw_evidence.get("evidence_source")
            if not isinstance(evidence_id, str) or not evidence_id.strip() or not isinstance(evidence_source, str) or not evidence_source.strip():
                raise ValueError("ledger de execução inválido.")
            normalized_evidence_id = evidence_id.strip()
            if normalized_evidence_id in seen_evidence_ids:
                raise ValueError("ledger de execução inválido: evidence_id duplicado.")
            seen_evidence_ids.add(normalized_evidence_id)
            evidence[request_id] = {"evidence_id": normalized_evidence_id, "evidence_source": evidence_source.strip()}

        context: dict[str, dict[str, str | None]] = {}
        seen_external_ids: set[str] = set()
        for request_id, raw_context in context_payload.items():
            if request_id not in states or not isinstance(raw_context, dict):
                raise ValueError("ledger de execução inválido.")
            broker_id = raw_context.get("broker_id")
            symbol = raw_context.get("symbol")
            external_id = raw_context.get("external_id")
            if not isinstance(broker_id, str) or not broker_id.strip() or not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("ledger de execução inválido.")
            if external_id is not None and (not isinstance(external_id, str) or not external_id.strip()):
                raise ValueError("ledger de execução inválido.")
            normalized_external_id = external_id.strip() if isinstance(external_id, str) else None
            if normalized_external_id is not None:
                if normalized_external_id in seen_external_ids:
                    raise ValueError("ledger de execução inválido: external_id duplicado.")
                seen_external_ids.add(normalized_external_id)
            context[request_id] = {"broker_id": broker_id.strip(), "symbol": symbol.strip(), "external_id": normalized_external_id}
        return states, evidence, context

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(json.dumps({
            "states": {key: self._states[key].value for key in sorted(self._states)},
            "reconciliation_evidence": {key: self._reconciliation_evidence[key] for key in sorted(self._reconciliation_evidence)},
            "execution_context": {key: self._execution_context[key] for key in sorted(self._execution_context)},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    def _mutate_locked(self, mutation) -> None:
        with self._process_lock():
            self._load()
            mutation()
            self._write()

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        self._validate_id(request_id)
        with self._process_lock():
            self._load()
            return self._states.get(request_id)

    def snapshot(self) -> dict[str, ExecutionLedgerStatus]:
        with self._process_lock():
            self._load()
            return dict(self._states)

    def contains(self, request_id: str) -> bool:
        return self.status(request_id) is not None

    def reconciliation_evidence(self, request_id: str) -> dict[str, str] | None:
        self._validate_id(request_id)
        with self._process_lock():
            self._load()
            evidence = self._reconciliation_evidence.get(request_id)
            return dict(evidence) if evidence is not None else None

    def execution_context(self, request_id: str) -> dict[str, str | None] | None:
        self._validate_id(request_id)
        with self._process_lock():
            self._load()
            context = self._execution_context.get(request_id)
            return dict(context) if context is not None else None

    def reserve(self, request_id: str) -> None:
        self._validate_id(request_id)
        def mutation() -> None:
            if request_id in self._states:
                raise ValueError("request_id já possui estado; replay REAL recusado.")
            self._states[request_id] = ExecutionLedgerStatus.RESERVED
        self._mutate_locked(mutation)

    def reserve_real(self, request_id: str, *, broker_id: str, symbol: str) -> None:
        self._validate_id(request_id)
        if not isinstance(broker_id, str) or not broker_id.strip() or not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("identidade REAL de broker e símbolo é obrigatória.")
        def mutation() -> None:
            if request_id in self._states:
                raise ValueError("request_id já possui estado; replay REAL recusado.")
            self._states[request_id] = ExecutionLedgerStatus.RESERVED
            self._execution_context[request_id] = {"broker_id": broker_id.strip(), "symbol": symbol.strip(), "external_id": None}
        self._mutate_locked(mutation)

    def record(self, request_id: str) -> None:
        self._validate_id(request_id)
        def mutation() -> None:
            if request_id not in self._states:
                self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.ACCEPTED)

    def mark_accepted_real(self, request_id: str, *, external_id: str) -> None:
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id REAL é obrigatório.")
        normalized_external_id = external_id.strip()
        def mutation() -> None:
            current = self._states.get(request_id)
            context = self._execution_context.get(request_id)
            if current is not ExecutionLedgerStatus.RESERVED or context is None:
                raise ValueError("contexto REAL não está reservado para aceite terminal.")
            for other_request_id, other_context in self._execution_context.items():
                if other_request_id != request_id and other_context.get("external_id") == normalized_external_id:
                    raise ValueError("external_id REAL já está vinculado a outra operação.")
            if context.get("external_id") not in (None, normalized_external_id):
                raise ValueError("external_id REAL não pode ser substituído.")
            context["external_id"] = normalized_external_id
            self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
        self._mutate_locked(mutation)

    def mark_rejected(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.UNKNOWN)

    def reconcile(self, request_id: str, *, executed: bool, evidence_id: str | None = None, evidence_source: str | None = None) -> None:
        self._validate_id(request_id)
        if not isinstance(evidence_id, str) or not evidence_id.strip() or not isinstance(evidence_source, str) or not evidence_source.strip():
            raise ValueError("reconciliação exige evidence_id e evidence_source válidos")
        normalized_evidence_id = evidence_id.strip()
        normalized_evidence_source = evidence_source.strip()
        def mutation() -> None:
            if self._states.get(request_id) not in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                raise ValueError("request_id não está em estado incerto reconciliável.")
            for other_request_id, other_evidence in self._reconciliation_evidence.items():
                if other_request_id != request_id and other_evidence.get("evidence_id") == normalized_evidence_id:
                    raise ValueError("evidence_id já está vinculado a outra operação.")
            self._states[request_id] = ExecutionLedgerStatus.RECONCILED_EXECUTED if executed else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
            self._reconciliation_evidence[request_id] = {"evidence_id": normalized_evidence_id, "evidence_source": normalized_evidence_source}
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
            allowed = {
                ExecutionLedgerStatus.ACCEPTED: (ExecutionLedgerStatus.RESERVED,),
                ExecutionLedgerStatus.REJECTED: (ExecutionLedgerStatus.RESERVED,),
                ExecutionLedgerStatus.UNKNOWN: (ExecutionLedgerStatus.RESERVED,),
            }
            if current not in allowed.get(status, ()):
                raise ValueError(f"transição inválida de {current.value} para {status.value}.")
            self._states[request_id] = status
        self._mutate_locked(mutation)
