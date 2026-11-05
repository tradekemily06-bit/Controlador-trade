from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
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


class PositionCloseState(str, Enum):
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"  # Legacy persisted value; new reconciliations use CLOSED.
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PositionCloseRecord:
    request_id: str
    external_id: str
    state: PositionCloseState
    updated_at: datetime
    close_external_id: str | None = None
    message: str = ""


class PositionCloseStore:
    """Durable, fail-closed idempotency boundary for position close requests."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, PositionCloseRecord] = {}
        self._load()

    @staticmethod
    def _validate(record: PositionCloseRecord) -> None:
        if not isinstance(record.request_id, str) or not record.request_id.strip():
            raise ValueError("request_id de fechamento inválido.")
        if not isinstance(record.external_id, str) or not record.external_id.strip():
            raise ValueError("external_id de fechamento inválido.")
        if not isinstance(record.state, PositionCloseState):
            raise ValueError("estado de fechamento inválido.")
        if not isinstance(record.updated_at, datetime):
            raise ValueError("timestamp de fechamento inválido.")
        if record.close_external_id is not None and (
            not isinstance(record.close_external_id, str) or not record.close_external_id.strip()
        ):
            raise ValueError("close_external_id inválido.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem de fechamento inválida.")

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError
            records: dict[str, PositionCloseRecord] = {}
            for item in payload:
                if not isinstance(item, dict):
                    raise ValueError
                record = PositionCloseRecord(
                    request_id=item["request_id"],
                    external_id=item["external_id"],
                    state=PositionCloseState(item["state"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                    close_external_id=item.get("close_external_id"),
                    message=item.get("message", ""),
                )
                self._validate(record)
                if record.request_id in records:
                    raise ValueError
                records[record.request_id] = record
            self._records = records
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("registro persistido de fechamento inválido.") from exc

    def get(self, request_id: str) -> PositionCloseRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        self._load()
        return self._records.get(request_id)

    def begin(self, request_id: str, external_id: str) -> PositionCloseRecord:
        record = PositionCloseRecord(
            request_id=request_id,
            external_id=external_id,
            state=PositionCloseState.REQUESTED,
            updated_at=datetime.now(timezone.utc),
        )
        self._validate(record)

        def mutation() -> None:
            previous = self._records.get(request_id)
            if previous is not None:
                if previous.external_id != external_id:
                    raise ValueError("request_id já possui fechamento associado a outro external_id.")
                if previous.state is not PositionCloseState.OPEN:
                    raise ValueError(
                        "fechamento já solicitado ou concluído; nova tentativa automática bloqueada até reconciliação."
                    )
            self._records[request_id] = record

        self._mutate_locked(mutation)
        return record

    def finish(
        self,
        request_id: str,
        state: PositionCloseState,
        *,
        message: str,
        close_external_id: str | None = None,
    ) -> PositionCloseRecord:
        if state not in (PositionCloseState.CLOSED, PositionCloseState.UNKNOWN):
            raise ValueError("resultado de fechamento inválido.")
        if not isinstance(message, str):
            raise ValueError("mensagem de fechamento inválida.")
        result: PositionCloseRecord | None = None

        def mutation() -> None:
            nonlocal result
            previous = self._records.get(request_id)
            if previous is None:
                raise ValueError("solicitação de fechamento não encontrada.")
            if previous.state is not PositionCloseState.REQUESTED:
                raise ValueError("fechamento já saiu do estado REQUESTED.")
            result = PositionCloseRecord(
                request_id=request_id,
                external_id=previous.external_id,
                state=state,
                updated_at=datetime.now(timezone.utc),
                close_external_id=close_external_id,
                message=message,
            )
            self._validate(result)
            self._records[request_id] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def reconcile(
        self,
        request_id: str,
        state: PositionCloseState,
        *,
        message: str,
    ) -> PositionCloseRecord:
        if state not in (PositionCloseState.CLOSED, PositionCloseState.OPEN, PositionCloseState.UNKNOWN):
            raise ValueError("estado de reconciliação de fechamento inválido.")
        if not isinstance(message, str):
            raise ValueError("mensagem de reconciliação inválida.")
        result: PositionCloseRecord | None = None

        def mutation() -> None:
            nonlocal result
            previous = self._records.get(request_id)
            if previous is None:
                raise ValueError("solicitação de fechamento não encontrada.")
            if previous.state not in (PositionCloseState.REQUESTED, PositionCloseState.UNKNOWN):
                raise ValueError("somente fechamento REQUESTED ou UNKNOWN pode ser reconciliado.")
            result = PositionCloseRecord(
                request_id=request_id,
                external_id=previous.external_id,
                state=state,
                updated_at=datetime.now(timezone.utc),
                close_external_id=previous.close_external_id,
                message=message,
            )
            self._validate(result)
            self._records[request_id] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def records(self) -> tuple[PositionCloseRecord, ...]:
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps([
                {
                    "request_id": r.request_id,
                    "external_id": r.external_id,
                    "state": r.state.value,
                    "updated_at": r.updated_at.isoformat(),
                    "close_external_id": r.close_external_id,
                    "message": r.message,
                }
                for r in (self._records[key] for key in sorted(self._records))
            ], ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
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
                self._save()
            finally:
                if msvcrt is not None:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
