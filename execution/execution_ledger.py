from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path

from core.runtime_checkpoint import process_file_lock


class ExecutionLedgerStatus(str, Enum):
    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED_EXECUTED = "RECONCILED_EXECUTED"
    RECONCILED_NOT_EXECUTED = "RECONCILED_NOT_EXECUTED"


class ExecutionLedger:
    """Persistent request state and broker reference for restart-safe execution."""

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
        self._states = self._decode(payload)
        self._external_ids = self._decode_external_ids(payload, self._states)

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
            if isinstance(raw_status, dict):
                raw_status = raw_status.get("status")
            try:
                status = ExecutionLedgerStatus(raw_status)
            except (TypeError, ValueError) as exc:
                raise ValueError("ledger de execução inválido.") from exc
            states[request_id] = status
        return states

    @staticmethod
    def _decode_external_ids(
        payload: object, states: dict[str, ExecutionLedgerStatus]
    ) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        external_ids: dict[str, str] = {}
        for request_id, raw_status in payload.items():
            if not isinstance(raw_status, dict):
                continue
            external_id = raw_status.get("external_id")
            if external_id is None:
                if states.get(request_id) is ExecutionLedgerStatus.RECONCILED_EXECUTED:
                    raise ValueError("ledger de execução inválido: RECONCILED_EXECUTED exige external_id.")
                continue
            if not isinstance(external_id, str) or not external_id.strip():
                raise ValueError("ledger de execução inválido.")
            if states.get(request_id) in (ExecutionLedgerStatus.REJECTED, ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED):
                raise ValueError("ledger de execução inválido: estado não executado possui external_id.")
            normalized_external_id = external_id.strip()
            if normalized_external_id in external_ids.values():
                raise ValueError("ledger de execução inválido: external_id duplicado.")
            external_ids[request_id] = normalized_external_id
        for request_id, status in states.items():
            if status is ExecutionLedgerStatus.RECONCILED_EXECUTED and request_id not in external_ids:
                raise ValueError("ledger de execução inválido: RECONCILED_EXECUTED exige external_id.")
        return external_ids

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {}
        for key in sorted(self._states):
            status = self._states[key].value
            external_id = self._external_ids.get(key)
            payload[key] = (
                {"status": status, "external_id": external_id}
                if external_id is not None
                else status
            )
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        if os.name != "nt":
            with self.path.open("rb") as handle:
                os.fsync(handle.fileno())
        try:
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass

    def _mutate_locked(self, mutation) -> None:
        """Serialize lifecycle read/modify/write so processes cannot lose updates."""
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        with process_file_lock(lock_path):
            self._load()
            mutation()
            self._write()

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        self._validate_id(request_id)
        self._load()
        return self._states.get(request_id)

    def external_id(self, request_id: str) -> str | None:
        self._validate_id(request_id)
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
        self._validate_id(request_id)

        def mutation() -> None:
            if request_id not in self._states:
                raise ValueError("request_id não foi reservado; record() não pode criar aceite fora da barreira.")
            if self._states[request_id] is not ExecutionLedgerStatus.RESERVED:
                raise ValueError("record() não pode promover estado UNKNOWN/terminal sem reconciliação explícita.")
            self._states[request_id] = ExecutionLedgerStatus.ACCEPTED

        self._mutate_locked(mutation)

    def bind_external_id(self, request_id: str, external_id: str) -> None:
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido.")

        normalized = external_id.strip()

        def mutation() -> None:
            if request_id not in self._states:
                raise ValueError("request_id não foi reservado.")
            if self._states[request_id] not in (
                ExecutionLedgerStatus.RESERVED,
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.ACCEPTED,
            ):
                raise ValueError("external_id não pode ser vinculado a estado terminal rejeitado.")
            owner = next(
                (rid for rid, value in self._external_ids.items() if value == normalized and rid != request_id),
                None,
            )
            if owner is not None:
                raise ValueError("external_id já está vinculado a outro request_id.")
            existing = self._external_ids.get(request_id)
            if existing is not None and existing != normalized:
                raise ValueError("request_id já possui external_id diferente.")
            self._external_ids[request_id] = normalized

        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.ACCEPTED)

    def mark_rejected(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.UNKNOWN)

    def reconcile(self, request_id: str, *, executed: bool, external_id: str | None = None) -> None:
        """Finalize an uncertain request from an explicit external observation.

        If the broker confirms execution, a durable external reference is mandatory.
        The binding and state transition happen under the same process lock so a crash
        cannot leave a reconciled execution without its broker identity.
        """
        self._validate_id(request_id)
        if external_id is not None and (
            not isinstance(external_id, str) or not external_id.strip()
        ):
            raise ValueError("external_id inválido.")

        normalized_external_id = external_id.strip() if isinstance(external_id, str) else None

        def mutation() -> None:
            current = self._states.get(request_id)
            if current not in (
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
            ):
                raise ValueError("request_id não está em estado incerto reconciliável.")

            existing = self._external_ids.get(request_id)
            resolved_external_id = normalized_external_id or existing
            if executed and not resolved_external_id:
                raise ValueError(
                    "reconciliação EXECUTED exige external_id durável."
                )

            if resolved_external_id is not None:
                owner = next(
                    (
                        rid
                        for rid, value in self._external_ids.items()
                        if value == resolved_external_id and rid != request_id
                    ),
                    None,
                )
                if owner is not None:
                    raise ValueError("external_id já está vinculado a outro request_id.")
                if existing is not None and existing != resolved_external_id:
                    raise ValueError("request_id já possui external_id diferente.")
                self._external_ids[request_id] = resolved_external_id

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
            allowed_sources = (
                (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN)
                if status is ExecutionLedgerStatus.UNKNOWN
                else (ExecutionLedgerStatus.RESERVED,)
            )
            if current not in allowed_sources:
                raise ValueError(
                    f"transição inválida de {current.value} para {status.value}; "
                    "estado UNKNOWN só pode sair por reconcile()."
                )
            self._states[request_id] = status

        self._mutate_locked(mutation)
