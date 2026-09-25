from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

from core.file_lock import locked_file


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
        self.path = Path(path)
        self._states: dict[str, ExecutionLedgerStatus] = {}
        self._reconciliation_evidence: dict[str, dict[str, str]] = {}
        self._execution_context: dict[str, dict[str, str | None]] = {}
        self._load()

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

        envelope = "states" in payload
        if envelope:
            states_payload = payload.get("states")
            evidence_payload = payload.get("reconciliation_evidence", {})
            context_payload = payload.get("execution_context", {})
            if not isinstance(states_payload, dict) or not isinstance(evidence_payload, dict) or not isinstance(context_payload, dict):
                raise ValueError("ledger de execução inválido.")
        else:
            states_payload, evidence_payload, context_payload = payload, {}, {}

        states: dict[str, ExecutionLedgerStatus] = {}
        for request_id, raw_status in states_payload.items():
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("ledger de execução inválido.")
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
            evidence_id = evidence_id.strip()
            if evidence_id in seen_evidence_ids:
                raise ValueError("ledger de execução inválido: evidence_id duplicado.")
            seen_evidence_ids.add(evidence_id)
            evidence[request_id] = {"evidence_id": evidence_id, "evidence_source": evidence_source.strip()}

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
            external_id = external_id.strip() if isinstance(external_id, str) else None
            if external_id is not None:
                if external_id in seen_external_ids:
                    raise ValueError("ledger de execução inválido: external_id duplicado.")
                seen_external_ids.add(external_id)
            context[request_id] = {"broker_id": broker_id.strip(), "symbol": symbol.strip(), "external_id": external_id}
        return states, evidence, context

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {
            "states": {key: self._states[key].value for key in sorted(self._states)},
            "reconciliation_evidence": {key: self._reconciliation_evidence[key] for key in sorted(self._reconciliation_evidence)},
            "execution_context": {key: self._execution_context[key] for key in sorted(self._execution_context)},
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def _mutate_locked(self, mutation) -> None:
        with locked_file(self.path.with_name(f".{self.path.name}.lock")):
            self._load()
            mutation()
            self._write()

    def _read_locked(self, reader):
        with locked_file(self.path.with_name(f".{self.path.name}.lock")):
            self._load()
            return reader()

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        self._validate_id(request_id)
        return self._read_locked(lambda: self._states.get(request_id))

    def contains(self, request_id: str) -> bool:
        return self.status(request_id) is not None

    def snapshot(self) -> dict[str, ExecutionLedgerStatus]:
        return self._read_locked(lambda: dict(self._states))

    def reconciliation_evidence(self, request_id: str) -> dict[str, str] | None:
        self._validate_id(request_id)
        return self._read_locked(lambda: dict(self._reconciliation_evidence[request_id]) if request_id in self._reconciliation_evidence else None)

    def execution_context(self, request_id: str) -> dict[str, str | None] | None:
        self._validate_id(request_id)
        return self._read_locked(lambda: dict(self._execution_context[request_id]) if request_id in self._execution_context else None)

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
            if request_id in self._execution_context:
                raise ValueError("record() genérico não pode finalizar uma reserva REAL.")
            if request_id not in self._states:
                self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.ACCEPTED)

    def mark_accepted_real(self, request_id: str, *, external_id: str) -> None:
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id REAL é obrigatório.")
        external_id = external_id.strip()
        def mutation() -> None:
            if self._states.get(request_id) is not ExecutionLedgerStatus.RESERVED:
                raise ValueError("request_id REAL não está reservado.")
            context = self._execution_context.get(request_id)
            if context is None:
                raise ValueError("contexto REAL ausente.")
            for other_id, other_context in self._execution_context.items():
                if other_id != request_id and other_context.get("external_id") == external_id:
                    raise ValueError("external_id REAL já está vinculado a outra operação.")
            context_external_id = context.get("external_id")
            if context_external_id not in (None, external_id):
                raise ValueError("external_id REAL não pode ser substituído.")
            context["external_id"] = external_id
            self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
        self._mutate_locked(mutation)

    def bind_external_id(self, request_id: str, *, external_id: str) -> None:
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id REAL é obrigatório.")
        external_id = external_id.strip()
        def mutation() -> None:
            current = self._states.get(request_id)
            if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                raise ValueError("external_id só pode ser associado enquanto a operação estiver incerta.")
            context = self._execution_context.get(request_id)
            if context is None:
                raise ValueError("contexto REAL ausente.")
            for other_id, other_context in self._execution_context.items():
                if other_id != request_id and other_context.get("external_id") == external_id:
                    raise ValueError("external_id REAL já está vinculado a outra operação.")
            existing = context.get("external_id")
            if existing not in (None, external_id):
                raise ValueError("external_id REAL não pode ser substituído.")
            context["external_id"] = external_id
        self._mutate_locked(mutation)

    def mark_rejected(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.UNKNOWN)

    def reconcile(self, request_id: str, *, executed: bool, evidence_id: str, evidence_source: str) -> None:
        self._validate_id(request_id)
        if not isinstance(evidence_id, str) or not evidence_id.strip() or not isinstance(evidence_source, str) or not evidence_source.strip():
            raise ValueError("reconciliação exige evidence_id e evidence_source válidos.")
        evidence_id, evidence_source = evidence_id.strip(), evidence_source.strip()
        def mutation() -> None:
            if self._states.get(request_id) not in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                raise ValueError("request_id não está em estado incerto reconciliável.")
            for other_id, evidence in self._reconciliation_evidence.items():
                if other_id != request_id and evidence.get("evidence_id") == evidence_id:
                    raise ValueError("evidence_id já está vinculado a outra operação.")
            self._states[request_id] = ExecutionLedgerStatus.RECONCILED_EXECUTED if executed else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
            self._reconciliation_evidence[request_id] = {"evidence_id": evidence_id, "evidence_source": evidence_source}
        self._mutate_locked(mutation)

    def request_id_for_external_id(self, external_id: str) -> str | None:
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id não pode ser vazio.")
        external_id = external_id.strip()
        def reader() -> str | None:
            matches = [
                request_id
                for request_id, context in self._execution_context.items()
                if context.get("external_id") == external_id
            ]
            if len(matches) > 1:
                raise ValueError("external_id vinculado a múltiplas operações.")
            return matches[0] if matches else None
        return self._read_locked(reader)

    def records(self) -> tuple[str, ...]:
        return self._read_locked(lambda: tuple(sorted(self._states)))

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
