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
    ACCEPTED = "ACCEPTED"  # Legacy persisted value.
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
    attempt: int = 1


class PositionCloseStore:
    """Durable, append-only attempt history and fail-closed close idempotency."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[tuple[str, int], PositionCloseRecord] = {}
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
        if isinstance(record.attempt, bool) or not isinstance(record.attempt, int) or record.attempt < 0:
            raise ValueError("número da observação/tentativa de fechamento inválido.")
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
            records: dict[tuple[str, int], PositionCloseRecord] = {}
            for item in payload:
                if not isinstance(item, dict):
                    raise ValueError
                persisted_state = PositionCloseState(item["state"])
                # Older versions used ACCEPTED for a broker response without
                # the current broker-evidence reconciliation contract. Do not
                # assume that such a position is closed: recover it as UNKNOWN.
                if persisted_state is PositionCloseState.ACCEPTED:
                    persisted_state = PositionCloseState.UNKNOWN
                record = PositionCloseRecord(
                    request_id=item["request_id"],
                    external_id=item["external_id"],
                    state=persisted_state,
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                    close_external_id=item.get("close_external_id"),
                    message=item.get("message", ""),
                    attempt=item.get("attempt", 1),
                )
                self._validate(record)
                key = (record.request_id, record.attempt)
                if key in records:
                    raise ValueError
                records[key] = record
            self._records = records
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("registro persistido de fechamento inválido.") from exc

    def _latest(self, request_id: str) -> PositionCloseRecord | None:
        matches = [
            record for (stored_id, _), record in self._records.items()
            if stored_id == request_id
        ]
        return max(matches, key=lambda record: record.attempt) if matches else None

    def get(self, request_id: str) -> PositionCloseRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        self._load()
        return self._latest(request_id)

    def begin(self, request_id: str, external_id: str) -> PositionCloseRecord:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id de fechamento inválido.")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id de fechamento inválido.")
        result: PositionCloseRecord | None = None

        def mutation() -> None:
            nonlocal result
            previous = self._latest(request_id)
            if previous is not None:
                if previous.external_id != external_id:
                    raise ValueError("request_id já possui fechamento associado a outro external_id.")
                if previous.state is not PositionCloseState.OPEN:
                    raise ValueError(
                        "fechamento já solicitado ou concluído; nova tentativa automática bloqueada até reconciliação."
                    )
                attempt = previous.attempt + 1
            else:
                attempt = 1
            result = PositionCloseRecord(
                request_id=request_id,
                external_id=external_id,
                state=PositionCloseState.REQUESTED,
                updated_at=datetime.now(timezone.utc),
                attempt=attempt,
            )
            self._validate(result)
            self._records[(request_id, attempt)] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

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
            previous = self._latest(request_id)
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
                attempt=previous.attempt,
            )
            self._validate(result)
            self._records[(request_id, previous.attempt)] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def observe_initial(
        self,
        request_id: str,
        external_id: str,
        state: PositionCloseState,
        *,
        message: str,
    ) -> PositionCloseRecord:
        """Persist first read-only broker observation without fabricating a close attempt."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id de observação inválido.")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id de observação inválido.")
        if state not in (PositionCloseState.CLOSED, PositionCloseState.OPEN, PositionCloseState.UNKNOWN):
            raise ValueError("estado de observação inválido.")
        if not isinstance(message, str):
            raise ValueError("mensagem de observação inválida.")
        result: PositionCloseRecord | None = None

        def mutation() -> None:
            nonlocal result
            previous = self._latest(request_id)
            if previous is not None:
                if previous.external_id != external_id.strip():
                    raise ValueError("observação já associada a outro external_id.")
                raise ValueError("já existe observação; use reconciliação.")
            result = PositionCloseRecord(
                request_id=request_id,
                external_id=external_id.strip(),
                state=state,
                updated_at=datetime.now(timezone.utc),
                message=message,
                attempt=0,
            )
            self._validate(result)
            self._records[(request_id, 0)] = result

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
            previous = self._latest(request_id)
            if previous is None:
                raise ValueError("solicitação de fechamento não encontrada.")
            if previous.state not in (PositionCloseState.REQUESTED, PositionCloseState.UNKNOWN, PositionCloseState.OPEN):
                raise ValueError("somente fechamento REQUESTED, UNKNOWN ou OPEN pode ser reconciliado.")
            result = PositionCloseRecord(
                request_id=request_id,
                external_id=previous.external_id,
                state=state,
                updated_at=datetime.now(timezone.utc),
                close_external_id=previous.close_external_id,
                message=message,
                attempt=previous.attempt,
            )
            self._validate(result)
            self._records[(request_id, previous.attempt)] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def records(self) -> tuple[PositionCloseRecord, ...]:
        self._load()
        latest: dict[str, PositionCloseRecord] = {}
        for record in self._records.values():
            current = latest.get(record.request_id)
            if current is None or record.attempt > current.attempt:
                latest[record.request_id] = record
        return tuple(latest[key] for key in sorted(latest))

    def history(self, request_id: str | None = None) -> tuple[PositionCloseRecord, ...]:
        self._load()
        records = self._records.values()
        if request_id is not None:
            if not isinstance(request_id, str) or not request_id.strip():
                raise ValueError("request_id não pode ser vazio.")
            records = (record for record in records if record.request_id == request_id)
        return tuple(sorted(records, key=lambda record: (record.request_id, record.attempt)))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps([
                {
                    "request_id": record.request_id,
                    "external_id": record.external_id,
                    "state": record.state.value,
                    "updated_at": record.updated_at.isoformat(),
                    "close_external_id": record.close_external_id,
                    "message": record.message,
                    "attempt": record.attempt,
                }
                for record in sorted(self._records.values(), key=lambda item: (item.request_id, item.attempt))
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
