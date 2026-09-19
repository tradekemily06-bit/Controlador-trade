from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

from core.durable_json import atomic_write_json, locked_path, read_json


class ExecutionLedgerStatus(str, Enum):
    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED_EXECUTED = "RECONCILED_EXECUTED"
    RECONCILED_NOT_EXECUTED = "RECONCILED_NOT_EXECUTED"


class ExecutionLedger:
    _request_lock_local = threading.local()
    _real_lock_local = threading.local()

    """Persistent request state for restart-safe REAL execution idempotency."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._states: dict[str, ExecutionLedgerStatus] = {}
        self._external_ids: dict[str, str] = {}
        self._load()

    def _load_unlocked(self) -> None:
        self._states = {}
        self._external_ids = {}
        try:
            payload = read_json(self.path, {})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states, self._external_ids = self._decode(payload)

    def _load(self) -> None:
        try:
            with locked_path(self.path):
                self._load_unlocked()
        except ValueError:
            raise
        except OSError as exc:
            raise ValueError("ledger de execução inválido.") from exc

    @staticmethod
    def _decode(payload: object) -> tuple[dict[str, ExecutionLedgerStatus], dict[str, str]]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() or item != item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return {item: ExecutionLedgerStatus.ACCEPTED for item in payload}, {}
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")
        states: dict[str, ExecutionLedgerStatus] = {}
        external_ids: dict[str, str] = {}
        for request_id, raw_status in payload.items():
            if not isinstance(request_id, str) or not request_id.strip() or request_id != request_id.strip():
                raise ValueError("ledger de execução inválido.")
            external_id = None
            if isinstance(raw_status, dict):
                if set(raw_status) - {"status", "external_id"}:
                    raise ValueError("ledger de execução inválido.")
                raw_value = raw_status.get("status")
                external_id = raw_status.get("external_id")
                if external_id is not None and (not isinstance(external_id, str) or not external_id.strip()):
                    raise ValueError("ledger de execução inválido.")
            else:
                raw_value = raw_status
            try:
                states[request_id] = ExecutionLedgerStatus(raw_value)
            except (ValueError, TypeError) as exc:
                raise ValueError("ledger de execução inválido.") from exc
            if external_id is not None:
                normalized_external_id = external_id.strip()
                if states[request_id] is ExecutionLedgerStatus.REJECTED:
                    raise ValueError("ledger de execução inválido; REJECTED não pode possuir external_id.")
                if normalized_external_id in external_ids.values():
                    raise ValueError("ledger de execução inválido; external_id duplicado.")
                external_ids[request_id] = normalized_external_id
        return states, external_ids

    def _write_unlocked(self) -> None:
        payload = {
            key: {
                "status": self._states[key].value,
                **({"external_id": self._external_ids[key]} if key in self._external_ids else {}),
            }
            for key in sorted(self._states)
        }
        atomic_write_json(self.path, payload)

    def _mutate_locked(self, mutation) -> None:
        """Serialize read/modify/write so two processes cannot reserve the same ID."""
        try:
            with locked_path(self.path):
                self._load_unlocked()
                mutation()
                self._write_unlocked()
        except ValueError:
            raise
        except OSError as exc:
            raise OSError("não foi possível persistir o ledger de execução.") from exc

    @contextmanager
    def real_execution_lock(self):
        """Serialize global REAL dispatch with recovery/reconciliation state changes.

        This is intentionally distinct from the per-request lock: a global recovery
        barrier can become unsafe because of another request. The final REAL broker
        boundary must therefore share one process/host durable lock with workers that
        can mutate uncertain execution state.
        """
        lock_path = self.path.with_name(f".{self.path.name}.real-execution.lock")
        held = getattr(self._real_lock_local, "held", set())
        if lock_path in held:
            yield
            return
        with locked_path(lock_path):
            held.add(lock_path)
            self._real_lock_local.held = held
            try:
                yield
            finally:
                held.discard(lock_path)
                self._real_lock_local.held = held

    def request_execution_lock(self, request_id: str):
        """Validate the request identity immediately, then return its lock context."""
        if not isinstance(request_id, str) or not request_id.strip() or request_id != request_id.strip():
            raise ValueError("request_id inválido ou não canônico.")
        return self._request_execution_lock_context(request_id)

    @contextmanager
    def _request_execution_lock_context(self, request_id: str):
        # Never place the raw request_id in a filesystem path. Even though
        # request IDs are normally generated internally, a public execution
        # boundary must not turn an untrusted identifier into a path segment.
        request_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        lock_path = self.path.with_name(
            f".{self.path.name}.{request_key}.execution.lock"
        )
        held = getattr(self._request_lock_local, "held", set())
        if lock_path in held:
            yield
            return
        with locked_path(lock_path):
            held.add(lock_path)
            self._request_lock_local.held = held
            try:
                yield
            finally:
                held.discard(lock_path)
                self._request_lock_local.held = held
        # Keep the hashed lock inode stable. Removing it here would allow a
        # second process still waiting on the old inode to overlap with a third
        # process that creates a new inode at the same path.


    def external_id(self, request_id: str) -> str | None:
        self._validate_id(request_id)
        self._load()
        return self._external_ids.get(request_id)

    def bind_external_id(self, request_id: str, external_id: str) -> None:
        """Bind external identity under the same per-request lock as REAL dispatch."""
        with self.request_execution_lock(request_id):
            self._bind_external_id_locked(request_id, external_id)

    def _bind_external_id_locked(self, request_id: str, external_id: str) -> None:
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id não pode ser vazio.")

        def mutation() -> None:
            if request_id not in self._states:
                raise ValueError("request_id não foi reservado.")
            existing = self._external_ids.get(request_id)
            normalized = external_id.strip()
            if existing is not None and existing != normalized:
                raise ValueError("external_id conflitante para o mesmo request_id.")
            if normalized in self._external_ids.values() and existing != normalized:
                raise ValueError("external_id já está associado a outro request_id.")
            current = self._states[request_id]
            if current is ExecutionLedgerStatus.REJECTED:
                raise ValueError("estado REJECTED não pode receber external_id após rejeição definitiva.")
            if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.ACCEPTED, ExecutionLedgerStatus.RECONCILED_EXECUTED, ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED):
                raise ValueError(f"estado inválido para vínculo de external_id: {current.value}.")
            self._external_ids[request_id] = normalized

        self._mutate_locked(mutation)

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        self._validate_id(request_id)
        self._load()
        return self._states.get(request_id)

    def contains(self, request_id: str) -> bool:
        return self.status(request_id) is not None

    def reserve(self, request_id: str) -> None:
        """Reserve a request under its identity lock.

        REAL callers that need the global execution barrier acquire
        real_execution_lock() explicitly and then call _reserve_locked().
        Keeping the generic Ledger API mode-agnostic prevents DEMO callers from
        accidentally entering the REAL global barrier.
        """
        with self.request_execution_lock(request_id):
            self._reserve_locked(request_id)

    def _reserve_locked(self, request_id: str) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            if request_id in self._states:
                raise ValueError("request_id já possui estado; replay REAL recusado.")
            self._states[request_id] = ExecutionLedgerStatus.RESERVED

        self._mutate_locked(mutation)

    def record(self, request_id: str) -> None:
        """Legacy DEMO compatibility: finalize only an already-reserved request.

        This method is deliberately not an admission primitive. A missing
        request_id must never be manufactured directly as ACCEPTED, because that
        would create a durable execution state without passing through the
        execution gateway's reservation boundary.
        """
        with self.request_execution_lock(request_id):
            self._record_locked(request_id)

    def _record_locked(self, request_id: str) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado; record() não pode criar autoridade terminal.")
            if current is ExecutionLedgerStatus.UNKNOWN:
                raise ValueError("estado UNKNOWN requer reconciliação explícita.")
            if current is not ExecutionLedgerStatus.RESERVED:
                raise ValueError(f"record() exige estado RESERVED, encontrado {current.value}.")
            self._states[request_id] = ExecutionLedgerStatus.ACCEPTED

        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str) -> None:
        with self.request_execution_lock(request_id):
            self._transition_locked(request_id, ExecutionLedgerStatus.ACCEPTED)

    def mark_rejected(self, request_id: str) -> None:
        with self.request_execution_lock(request_id):
            self._transition_locked(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str) -> None:
        with self.request_execution_lock(request_id):
            self._transition_locked(request_id, ExecutionLedgerStatus.UNKNOWN)

    def _transition_locked(self, request_id: str, status: ExecutionLedgerStatus) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado.")
            if current is ExecutionLedgerStatus.UNKNOWN and status is not ExecutionLedgerStatus.UNKNOWN:
                raise ValueError("estado UNKNOWN requer reconciliação explícita.")
            if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                raise ValueError(f"transição inválida de {current.value} para {status.value}.")
            if status is ExecutionLedgerStatus.REJECTED and request_id in self._external_ids:
                raise ValueError("não é permitido rejeitar definitivamente um request com external_id.")
            self._states[request_id] = status

        self._mutate_locked(mutation)

    def _reconcile_locked(self, request_id: str, *, executed: bool) -> ExecutionLedgerStatus:
        self._validate_id(request_id)
        target = ExecutionLedgerStatus.RECONCILED_EXECUTED if executed else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED

        def mutation() -> None:
            current = self._states.get(request_id)
            if current not in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                raise ValueError("somente estados UNKNOWN/RESERVED podem ser reconciliados.")
            self._states[request_id] = target

        self._mutate_locked(mutation)

    def records(self) -> tuple[str, ...]:
        self._load()
        return tuple(sorted(self._states))

    def statuses(self) -> dict[str, ExecutionLedgerStatus]:
        """Return one fresh durable snapshot for recovery/observability checks."""
        self._load()
        return dict(self._states)

    @staticmethod
    def _validate_id(request_id: str) -> None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        if request_id != request_id.strip():
            raise ValueError("request_id inválido ou não canônico.")

