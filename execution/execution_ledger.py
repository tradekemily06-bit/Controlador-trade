from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None


class ExecutionLedgerStatus(str, Enum):
    RESERVED = "RESERVED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED_EXECUTED = "RECONCILED_EXECUTED"
    RECONCILED_NOT_EXECUTED = "RECONCILED_NOT_EXECUTED"


@dataclass(frozen=True)
class ExecutionLedgerEntry:
    status: ExecutionLedgerStatus
    external_id: str | None = None


class ExecutionLedger:
    """Authoritative durable REAL request state and broker reference.

    Legacy status-only JSON is parsed conservatively. Terminal states that
    require broker evidence but lack a durable external_id are quarantined as
    UNKNOWN rather than being trusted as new terminal authority. New accepted
    results persist external_id together with the terminal state so a crash
    after broker acceptance cannot erase the reconciliation handle.
    """

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._states: dict[str, ExecutionLedgerEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("ledger de execução inválido.") from exc
        self._states = self._decode(payload)

    @staticmethod
    def _decode(payload: object) -> dict[str, ExecutionLedgerEntry]:
        if isinstance(payload, list):
            if any(not isinstance(item, str) or not item.strip() for item in payload):
                raise ValueError("ledger de execução inválido.")
            return {
                item: ExecutionLedgerEntry(ExecutionLedgerStatus.UNKNOWN)
                for item in payload
            }
        if not isinstance(payload, dict):
            raise ValueError("ledger de execução inválido.")

        states: dict[str, ExecutionLedgerEntry] = {}
        for request_id, raw in payload.items():
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("ledger de execução inválido.")
            if isinstance(raw, str):
                try:
                    status = ExecutionLedgerStatus(raw)
                except ValueError as exc:
                    raise ValueError("ledger de execução inválido.") from exc
                if status in (
                    ExecutionLedgerStatus.ACCEPTED,
                    ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ):
                    status = ExecutionLedgerStatus.UNKNOWN
                states[request_id] = ExecutionLedgerEntry(status)
                continue
            if not isinstance(raw, dict):
                raise ValueError("ledger de execução inválido.")
            try:
                status = ExecutionLedgerStatus(raw["status"])
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError("ledger de execução inválido.") from exc
            external_id = raw.get("external_id")
            if external_id is not None and (
                not isinstance(external_id, str) or not external_id.strip()
            ):
                raise ValueError("external_id persistido inválido.")
            # A hand-edited or old structured record must not manufacture
            # terminal REAL authority merely by naming a terminal status.
            # Evidence-bearing terminal states require a durable broker ID.
            if status in (
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ) and external_id is None:
                status = ExecutionLedgerStatus.UNKNOWN
            states[request_id] = ExecutionLedgerEntry(status, external_id)
        return states

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {
            key: {
                "status": self._states[key].status.value,
                "external_id": self._states[key].external_id,
            }
            for key in sorted(self._states)
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        with temporary.open("rb") as durable_file:
            durable_file.flush()
            os.fsync(durable_file.fileno())
        os.replace(temporary, self.path)
        if fcntl is not None:
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

    def _mutate_locked(self, mutation) -> None:
        """Serialize read/modify/write; callers may hold the REAL global lock."""
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            elif msvcrt is not None:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                except OSError as exc:
                    raise OSError("não foi possível adquirir lock do ledger.") from exc
            else:
                raise OSError("ledger exige lock interprocesso suportado pelo sistema.")
            try:
                self._load()
                mutation()
                self._write()
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:
                    try:
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass

    def status(self, request_id: str) -> ExecutionLedgerStatus | None:
        self._validate_id(request_id)
        self._load()
        entry = self._states.get(request_id)
        return entry.status if entry else None

    def external_id(self, request_id: str) -> str | None:
        self._validate_id(request_id)
        self._load()
        entry = self._states.get(request_id)
        return entry.external_id if entry else None

    def entry(self, request_id: str) -> ExecutionLedgerEntry | None:
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
            self._states[request_id] = ExecutionLedgerEntry(ExecutionLedgerStatus.RESERVED)

        self._mutate_locked(mutation)

    def mark_accepted(self, request_id: str, external_id: str | None = None) -> None:
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id é obrigatório para ACCEPTED.")
        self._transition(
            request_id,
            ExecutionLedgerStatus.ACCEPTED,
            external_id=external_id,
        )

    def attach_external_id(self, request_id: str, external_id: str) -> None:
        self._validate_id(request_id)
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido.")

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None or current.status not in (
                ExecutionLedgerStatus.RESERVED,
                ExecutionLedgerStatus.UNKNOWN,
            ):
                raise ValueError("external_id só pode ser associado a estado incerto/reservado.")
            if current.external_id is not None and current.external_id != external_id:
                raise ValueError("external_id conflitante.")
            self._states[request_id] = ExecutionLedgerEntry(
                current.status,
                external_id,
            )

        self._mutate_locked(mutation)

    def mark_rejected(self, request_id: str, external_id: str | None = None) -> None:
        if external_id is not None and (
            not isinstance(external_id, str) or not external_id.strip()
        ):
            raise ValueError("external_id inválido.")
        self._transition(
            request_id,
            ExecutionLedgerStatus.REJECTED,
            external_id=external_id,
        )

    def mark_unknown(self, request_id: str) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado.")
            if current.status is not ExecutionLedgerStatus.RESERVED:
                raise ValueError(
                    f"transição inválida de {current.status.value} para UNKNOWN."
                )
            # UNKNOWN is a safety barrier, but the broker reference is still
            # valuable evidence. Never discard a durable external_id here.
            self._states[request_id] = ExecutionLedgerEntry(
                ExecutionLedgerStatus.UNKNOWN,
                current.external_id,
            )

        self._mutate_locked(mutation)

    def reconcile(
        self,
        request_id: str,
        *,
        executed: bool,
        external_id: str | None = None,
    ) -> None:
        self._validate_id(request_id)
        if external_id is not None and (
            not isinstance(external_id, str) or not external_id.strip()
        ):
            raise ValueError("external_id inválido.")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError(
                "external_id é obrigatório para qualquer reconciliação terminal."
            )

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None or current.status not in (
                ExecutionLedgerStatus.UNKNOWN,
                ExecutionLedgerStatus.RESERVED,
            ):
                raise ValueError("request_id não está em estado incerto reconciliável.")
            if (
                current.external_id is not None
                and external_id is not None
                and current.external_id != external_id
            ):
                raise ValueError("external_id conflitante na reconciliação.")
            resolved_external_id = external_id or current.external_id
            if not resolved_external_id:
                raise ValueError(
                    "external_id é obrigatório para qualquer reconciliação terminal."
                )
            self._states[request_id] = ExecutionLedgerEntry(
                ExecutionLedgerStatus.RECONCILED_EXECUTED
                if executed
                else ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
                resolved_external_id,
            )

        self._mutate_locked(mutation)

    def records(self) -> tuple[str, ...]:
        self._load()
        return tuple(sorted(self._states))

    @staticmethod
    def _validate_id(request_id: str) -> None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")

    def _transition(
        self,
        request_id: str,
        status: ExecutionLedgerStatus,
        *,
        external_id: str | None = None,
    ) -> None:
        self._validate_id(request_id)

        def mutation() -> None:
            current = self._states.get(request_id)
            if current is None:
                raise ValueError("request_id não foi reservado.")
            if current.status is not ExecutionLedgerStatus.RESERVED:
                raise ValueError(
                    f"transição inválida de {current.status.value} para {status.value}."
                )
            self._states[request_id] = ExecutionLedgerEntry(status, external_id)

        self._mutate_locked(mutation)
