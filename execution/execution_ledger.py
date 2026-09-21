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
except ImportError:  # pragma: no cover - POSIX
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
        self.path = Path(path).expanduser().resolve()
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
        except ValueError:
            raise
        self._states, self._external_ids = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> tuple[dict[str, ExecutionLedgerStatus], dict[str, str]]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return ({item: ExecutionLedgerStatus.ACCEPTED for item in payload}, {})
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")
        states: dict[str, ExecutionLedgerStatus] = {}
        external_ids: dict[str, str] = {}
        for request_id, raw_status in payload.items():
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("ledger de execução inválido.")
            raw_state = raw_status.get("state") if isinstance(raw_status, dict) else raw_status
            external_id = raw_status.get("external_id") if isinstance(raw_status, dict) else None
            if external_id is not None and (not isinstance(external_id, str) or not external_id.strip()):
                raise ValueError("ledger de execução inválido.")
            try:
                status = ExecutionLedgerStatus(raw_state)
            except ValueError as exc:
                raise ValueError("ledger de execução inválido.") from exc
            if status in (
                ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ) and external_id is not None:
                raise ValueError("ledger de execução inválido: estado não executado possui external_id.")
            if status is ExecutionLedgerStatus.RECONCILED_EXECUTED and external_id is None:
                raise ValueError("ledger de execução inválido: RECONCILED_EXECUTED exige external_id.")
            states[request_id] = status
            if external_id is not None:
                normalized_external_id = external_id.strip()
                if normalized_external_id in external_ids.values():
                    raise ValueError("ledger de execução inválido: external_id duplicado.")
                external_ids[request_id] = normalized_external_id
        return states, external_ids

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {key: ({"state": self._states[key].value, "external_id": self._external_ids[key]} if key in self._external_ids else self._states[key].value) for key in sorted(self._states)}
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        if os.name != "nt":
            with self.path.open("rb") as handle:
                os.fsync(handle.fileno())
        if os.name != "nt":
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

    def _lock_path(self) -> Path:
        return self.path.with_name(f".{self.path.name}.lock")

    @staticmethod
    def _lock(lock_file, *, exclusive: bool) -> None:
        if fcntl is not None:
            mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(lock_file.fileno(), mode)
            return
        if msvcrt is not None:
            lock_file.seek(0, 2)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            return
        raise RuntimeError("plataforma sem mecanismo de lock suportado.")

    @staticmethod
    def _unlock(lock_file) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)

    def _read_locked(self, reader):
        lock_path = self._lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            self._lock(lock_file, exclusive=False)
            try:
                self._load()
                return reader()
            finally:
                self._unlock(lock_file)

    def _mutate_locked(self, mutation) -> None:
        """Serialize read/modify/write so two processes cannot reserve the same ID."""
        lock_path = self._lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            self._lock(lock_file, exclusive=True)
            try:
                self._load()
                mutation()
                self._write()
            finally:
                self._unlock(lock_file)

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        request_id = self._normalize_id(request_id)
        return self._read_locked(lambda: self._states.get(request_id))

    def contains(self, request_id: str) -> bool:
        return self.status(request_id) is not None

    def reserve(self, request_id: str) -> None:
        request_id = self._normalize_id(request_id)

        def mutation() -> None:
            if request_id in self._states:
                raise ValueError("request_id já possui estado; replay REAL recusado.")
            self._states[request_id] = ExecutionLedgerStatus.RESERVED

        self._mutate_locked(mutation)

    def record(self, request_id: str) -> None:
        """Backward-compatible terminal record for existing DEMO infrastructure."""
        request_id = self._normalize_id(request_id)

        def mutation() -> None:
            if request_id not in self._states:
                self._states[request_id] = ExecutionLedgerStatus.ACCEPTED
            else:
                raise ValueError("record() não pode promover estado existente sem transição explícita.")

        self._mutate_locked(mutation)

    def external_id(self, request_id: str) -> str | None:
        request_id = self._normalize_id(request_id)
        return self._read_locked(lambda: self._external_ids.get(request_id))

    def bind_external_id(self, request_id: str, external_id: str) -> None:
        request_id = self._normalize_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id não pode ser vazio.")
        value = external_id.strip()
        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado.")
            if current in (
                ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ):
                raise ValueError("external_id não pode ser vinculado a estado terminal não executado.")
            existing = self._external_ids.get(request_id)
            if existing is not None and existing != value:
                raise ValueError("external_id não pode ser alterado após persistência.")
            if value in self._external_ids.values() and existing != value:
                raise ValueError("external_id já está vinculado a outro request_id.")
            self._external_ids[request_id] = value
        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.ACCEPTED)

    def mark_rejected(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.UNKNOWN)

    def reconcile(self, request_id: str, *, executed: bool, external_id: str | None = None) -> None:
        request_id = self._normalize_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            existing = self._external_ids.get(request_id)
            if not executed and existing is not None:
                raise ValueError("reconciliação NOT_EXECUTED contradiz external_id durável.")
            if executed:
                if external_id is None or not isinstance(external_id, str) or not external_id.strip():
                    raise ValueError("reconciliação EXECUTED exige external_id durável.")
                observed_external_id = external_id.strip()
                if existing is not None and existing != observed_external_id:
                    raise ValueError("external_id observado difere do external_id durável.")
                if existing is None:
                    # Recovery may legitimately discover the broker identity only
                    # after a crash between external acceptance and local binding.
                    # The observation is still constrained by the request_id,
                    # uniqueness check below, and the reconciliation boundary.
                    if observed_external_id in self._external_ids.values():
                        raise ValueError("external_id já está vinculado a outro request_id.")
                    self._external_ids[request_id] = observed_external_id
            allowed = (
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
                ExecutionLedgerStatus.ACCEPTED if executed else ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED if executed else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            )
            if current not in allowed:
                raise ValueError("request_id não está em estado reconciliável.")
            self._states[request_id] = (
                ExecutionLedgerStatus.RECONCILED_EXECUTED
                if executed
                else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
            )

        self._mutate_locked(mutation)

    def records(self) -> tuple[str, ...]:
        return self._read_locked(lambda: tuple(sorted(self._states)))

    @staticmethod
    def _normalize_id(request_id: str) -> str:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        return request_id.strip()

    def _transition(self, request_id: str, status: ExecutionLedgerStatus) -> None:
        request_id = self._normalize_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado.")
            if status is ExecutionLedgerStatus.UNKNOWN:
                if current not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                    raise ValueError(f"transição inválida de {current.value} para {status.value}.")
            elif current is not ExecutionLedgerStatus.RESERVED:
                raise ValueError(
                    f"transição terminal inválida de {current.value} para {status.value}; "
                    "UNKNOWN exige reconciliação explícita."
                )
            if status is ExecutionLedgerStatus.REJECTED and request_id in self._external_ids:
                raise ValueError("REJECTED não pode possuir external_id durável.")
            self._states[request_id] = status

        self._mutate_locked(mutation)
