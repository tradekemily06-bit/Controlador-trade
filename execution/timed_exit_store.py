from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None
try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX fallback
    msvcrt = None


@dataclass(frozen=True)
class TimedExitRecord:
    request_id: str
    cycle_id: str
    external_id: str
    account_fingerprint: str
    due_at: datetime
    next_attempt_at: datetime
    state: str = "SCHEDULED"
    attempts: int = 0
    message: str = ""


class TimedExitStore:
    """Durable best-effort DEMO exit schedule; it never sends broker orders."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path do agendador é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, TimedExitRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("agendamentos de saída temporizada inválidos.") from exc
        if not isinstance(payload, list):
            raise ValueError("agendamentos de saída temporizada inválidos.")
        records: dict[str, TimedExitRecord] = {}
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("registro de saída temporizada inválido.")
            try:
                record = TimedExitRecord(
                    request_id=item["request_id"],
                    cycle_id=item["cycle_id"],
                    external_id=item["external_id"],
                    account_fingerprint=item["account_fingerprint"],
                    due_at=datetime.fromisoformat(item["due_at"]),
                    next_attempt_at=datetime.fromisoformat(item["next_attempt_at"]),
                    state=item["state"],
                    attempts=item["attempts"],
                    message=item["message"],
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("registro de saída temporizada inválido.") from exc
            self._validate(record)
            if record.request_id in records:
                raise ValueError("request_id duplicado no agendador de saída temporizada.")
            records[record.request_id] = record
        self._records = records

    @staticmethod
    def _validate(record: TimedExitRecord) -> None:
        for value, label in (
            (record.request_id, "request_id"),
            (record.cycle_id, "cycle_id"),
            (record.external_id, "external_id"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} inválido no agendador.")
        if (
            not isinstance(record.account_fingerprint, str)
            or len(record.account_fingerprint) != 32
            or any(char not in "0123456789abcdef" for char in record.account_fingerprint)
        ):
            raise ValueError("identidade da conta inválida no agendador.")
        if record.due_at.tzinfo is None or record.next_attempt_at.tzinfo is None:
            raise ValueError("datas do agendador precisam conter fuso horário.")
        if record.state not in {"SCHEDULED", "CLOSED", "BLOCKED"}:
            raise ValueError("estado do agendador inválido.")
        if not isinstance(record.attempts, int) or isinstance(record.attempts, bool) or record.attempts < 0:
            raise ValueError("contador de tentativas inválido.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem do agendador inválida.")

    def schedule(
        self,
        *,
        request_id: str,
        cycle_id: str,
        external_id: str,
        account_fingerprint: str,
        delay_seconds: int,
        now: datetime | None = None,
    ) -> TimedExitRecord:
        if not isinstance(delay_seconds, int) or isinstance(delay_seconds, bool) or not 1 <= delay_seconds <= 86400:
            raise ValueError("delay_seconds deve estar entre 1 e 86400.")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now precisa conter fuso horário.")
        due = now.astimezone(timezone.utc) + timedelta(seconds=delay_seconds)
        candidate = TimedExitRecord(
            request_id=request_id.strip() if isinstance(request_id, str) else request_id,
            cycle_id=cycle_id.strip() if isinstance(cycle_id, str) else cycle_id,
            external_id=external_id.strip() if isinstance(external_id, str) else external_id,
            account_fingerprint=account_fingerprint,
            due_at=due,
            next_attempt_at=due,
        )
        self._validate(candidate)
        result: TimedExitRecord | None = None

        def mutation() -> None:
            nonlocal result
            previous = self._records.get(candidate.request_id)
            if previous is not None:
                if (
                    previous.cycle_id != candidate.cycle_id
                    or previous.external_id != candidate.external_id
                    or previous.account_fingerprint != candidate.account_fingerprint
                ):
                    raise ValueError("agendamento já vinculado a outra identidade de execução.")
                result = previous
                return
            self._records[candidate.request_id] = candidate
            result = candidate

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def due(self, *, now: datetime | None = None) -> tuple[TimedExitRecord, ...]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now precisa conter fuso horário.")
        self._load()
        current = now.astimezone(timezone.utc)
        return tuple(
            record for record in sorted(self._records.values(), key=lambda item: (item.next_attempt_at, item.request_id))
            if record.state == "SCHEDULED" and record.next_attempt_at <= current
        )

    def record_for(self, request_id: str) -> TimedExitRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        self._load()
        return self._records.get(request_id)

    def retry_later(self, request_id: str, *, message: str, delay_seconds: int = 5) -> TimedExitRecord:
        if not isinstance(delay_seconds, int) or isinstance(delay_seconds, bool) or not 1 <= delay_seconds <= 3600:
            raise ValueError("delay_seconds de retry inválido.")
        return self._update(
            request_id,
            lambda previous: TimedExitRecord(
                **{**previous.__dict__,
                   "next_attempt_at": datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
                   "attempts": previous.attempts + 1,
                   "message": message[:1000]}
            ),
        )

    def mark_closed(self, request_id: str, *, message: str) -> TimedExitRecord:
        return self._update(
            request_id,
            lambda previous: TimedExitRecord(
                **{**previous.__dict__, "state": "CLOSED", "attempts": previous.attempts + 1, "message": message[:1000]}
            ),
        )

    def block(self, request_id: str, *, message: str) -> TimedExitRecord:
        return self._update(
            request_id,
            lambda previous: TimedExitRecord(
                **{**previous.__dict__, "state": "BLOCKED", "attempts": previous.attempts + 1, "message": message[:1000]}
            ),
        )

    def records(self) -> tuple[TimedExitRecord, ...]:
        self._load()
        return tuple(self._records[key] for key in sorted(self._records))

    def _update(self, request_id: str, transform) -> TimedExitRecord:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        result: TimedExitRecord | None = None

        def mutation() -> None:
            nonlocal result
            previous = self._records.get(request_id)
            if previous is None:
                raise ValueError("agendamento de saída temporizada não encontrado.")
            result = transform(previous)
            self._validate(result)
            self._records[request_id] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        serialized = json.dumps([
            {
                "request_id": item.request_id,
                "cycle_id": item.cycle_id,
                "external_id": item.external_id,
                "account_fingerprint": item.account_fingerprint,
                "due_at": item.due_at.isoformat(),
                "next_attempt_at": item.next_attempt_at.isoformat(),
                "state": item.state,
                "attempts": item.attempts,
                "message": item.message,
            }
            for item in sorted(self._records.values(), key=lambda value: value.request_id)
        ], ensure_ascii=False, indent=2, sort_keys=True)
        # Flush the complete temporary file before replacing the previous
        # schedule. The account fingerprint is private runtime metadata.
        with temporary.open("w", encoding="utf-8", newline="\\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)
        if os.name != "nt":
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

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
