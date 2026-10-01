from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None
try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX fallback
    msvcrt = None


class ExecutionLedgerStatus(str, Enum):
    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED_EXECUTED = "RECONCILED_EXECUTED"
    RECONCILED_NOT_EXECUTED = "RECONCILED_NOT_EXECUTED"


@dataclass(frozen=True)
class ExecutionLedgerRecord:
    status: ExecutionLedgerStatus
    cycle_id: str | None = None
    external_id: str | None = None


class ExecutionLedger:
    """Persistent request state and durable execution identity mapping."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, ExecutionLedgerRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._records = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> dict[str, ExecutionLedgerRecord]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return {item: ExecutionLedgerRecord(ExecutionLedgerStatus.ACCEPTED) for item in payload}
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")
        records: dict[str, ExecutionLedgerRecord] = {}
        for request_id, raw in payload.items():
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("ledger de execução inválido.")
            if isinstance(raw, str):
                try:
                    records[request_id] = ExecutionLedgerRecord(ExecutionLedgerStatus(raw))
                except ValueError as exc:
                    raise ValueError("ledger de execução inválido.") from exc
                continue
            if not isinstance(raw, dict):
                raise ValueError("ledger de execução inválido.")
            try:
                status = ExecutionLedgerStatus(raw["status"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("ledger de execução inválido.") from exc
            cycle_id = raw.get("cycle_id")
            external_id = raw.get("external_id")
            if cycle_id is not None and (not isinstance(cycle_id, str) or not cycle_id.strip()):
                raise ValueError("ledger de execução inválido.")
            if external_id is not None and (not isinstance(external_id, str) or not external_id.strip()):
                raise ValueError("ledger de execução inválido.")
            records[request_id] = ExecutionLedgerRecord(
                status=status,
                cycle_id=cycle_id.strip() if cycle_id else None,
                external_id=external_id.strip() if external_id else None,
            )
        return records

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {
            key: {
                "status": record.status.value,
                **({"cycle_id": record.cycle_id} if record.cycle_id else {}),
                **({"external_id": record.external_id} if record.external_id else {}),
            }
            for key, record in sorted(self._records.items())
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def _mutate_locked(self, mutation) -> None:
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if msvcrt is not None:
                if os.fstat(lock_file.fileno()).st_size == 0:
                    lock_file.write("0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            elif fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                self._load()
                mutation()
                self._write()
            finally:
                if msvcrt is not None:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        record = self.record_for(request_id)
        return record.status if record is not None else None

    def record_for(self, request_id: str) -> ExecutionLedgerRecord | None:
        self._validate_id(request_id)
        self._load()
        return self._records.get(request_id)

    def contains(self, request_id: str) -> bool:
        return self.status(request_id) is not None

    def reserve(self, request_id: str, *, cycle_id: str | None = None) -> None:
        self._validate_id(request_id)
        self._validate_identity(cycle_id, "cycle_id")
        def mutation() -> None:
            if request_id in self._records:
                raise ValueError("request_id já possui estado; replay REAL recusado.")
            if cycle_id is not None and any(
                record.cycle_id == cycle_id.strip() for record in self._records.values()
            ):
                raise ValueError("cycle_id já possui uma execução registrada neste runtime.")
            self._records[request_id] = ExecutionLedgerRecord(
                ExecutionLedgerStatus.RESERVED,
                cycle_id.strip() if cycle_id else None,
            )
        self._mutate_locked(mutation)

    def record(self, request_id: str) -> None:
        self._validate_id(request_id)
        def mutation() -> None:
            if request_id not in self._records:
                self._records[request_id] = ExecutionLedgerRecord(ExecutionLedgerStatus.ACCEPTED)
        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.ACCEPTED)

    def mark_rejected(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.REJECTED)

    def mark_unknown(self, request_id: str) -> None:
        self._transition(request_id, ExecutionLedgerStatus.UNKNOWN)

    def bind_external_id(self, request_id: str, external_id: str) -> None:
        self._validate_id(request_id)
        self._validate_identity(external_id, "external_id", required=True)
        external_id = external_id.strip()
        def mutation() -> None:
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado.")
            if current.external_id is not None and current.external_id != external_id:
                raise ValueError("external_id já associado a outro identificador.")
            for other_request_id, other in self._records.items():
                if other_request_id != request_id and other.external_id == external_id:
                    raise ValueError("external_id já associado a outro request_id.")
            self._records[request_id] = ExecutionLedgerRecord(current.status, current.cycle_id, external_id)
        self._mutate_locked(mutation)

    def find_by_cycle_id(self, cycle_id: str) -> tuple[tuple[str, ExecutionLedgerRecord], ...]:
        self._validate_identity(cycle_id, "cycle_id", required=True)
        self._load()
        cycle_id = cycle_id.strip()
        return tuple((rid, rec) for rid, rec in sorted(self._records.items()) if rec.cycle_id == cycle_id)

    def reconcile(self, request_id: str, *, executed: bool) -> None:
        self._validate_id(request_id)
        def mutation() -> None:
            current = self._records.get(request_id)
            if current is None or current.status not in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.ACCEPTED):
                raise ValueError("request_id não está em estado incerto reconciliável.")
            self._records[request_id] = ExecutionLedgerRecord(
                ExecutionLedgerStatus.RECONCILED_EXECUTED if executed else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
                current.cycle_id,
                current.external_id,
            )
        self._mutate_locked(mutation)

    def records(self) -> tuple[str, ...]:
        self._load()
        return tuple(sorted(self._records))

    @staticmethod
    def _validate_id(request_id: str) -> None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")

    @staticmethod
    def _validate_identity(value: str | None, name: str, *, required: bool = False) -> None:
        if value is None and not required:
            return
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} não pode ser vazio.")

    def _transition(self, request_id: str, status: ExecutionLedgerStatus) -> None:
        self._validate_id(request_id)
        def mutation() -> None:
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado.")
            if current.status not in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                raise ValueError(f"transição inválida de {current.status.value} para {status.value}.")
            self._records[request_id] = ExecutionLedgerRecord(status, current.cycle_id, current.external_id)
        self._mutate_locked(mutation)

