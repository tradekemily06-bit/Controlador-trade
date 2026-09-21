from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
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


class ExecutionLifecycleState(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExecutionLifecycleRecord:
    request_id: str
    state: ExecutionLifecycleState
    updated_at: datetime
    message: str = ""


LIFECYCLE_RECOVERY_CAPABILITY = object()


class ExecutionLifecycleStore:
    """Durable execution state with cross-process mutation serialization."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path).expanduser().resolve()
        self._records: dict[str, ExecutionLifecycleRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError
            records: dict[str, ExecutionLifecycleRecord] = {}
            for item in payload:
                if not isinstance(item, dict):
                    raise ValueError
                record = ExecutionLifecycleRecord(
                    request_id=item["request_id"],
                    state=ExecutionLifecycleState(item["state"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                    message=item.get("message", ""),
                )
                self._validate(record)
                if record.request_id in records:
                    raise ValueError("ciclo de execução persistido inválido: request_id duplicado.")
                records[record.request_id] = record
            self._records = records
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc
        except ValueError:
            # Preserve precise lifecycle invariant failures for diagnostics.
            raise

    @staticmethod
    def _validate(record: ExecutionLifecycleRecord) -> None:
        if not isinstance(record.request_id, str) or not record.request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(record.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if (
            not isinstance(record.updated_at, datetime)
            or record.updated_at.tzinfo is None
            or record.updated_at.utcoffset() is None
        ):
            raise ValueError("timestamp inválido: deve ser timezone-aware.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem inválida.")

    def _lock_path(self) -> Path:
        return self.path.with_name(f".{self.path.name}.lock")

    def _with_lock(self):
        return self._lock_path().open("a+b")

    @staticmethod
    def _lock(lock_file) -> None:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            return
        if msvcrt is not None:
            # Windows msvcrt.locking() requires an existing byte range. Keep
            # the lock file non-empty before taking the one-byte lock.
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

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = [
            {
                "request_id": r.request_id,
                "state": r.state.value,
                "updated_at": r.updated_at.isoformat(),
                "message": r.message,
            }
            for r in sorted(self._records.values(), key=lambda item: item.request_id)
        ]
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
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

    def _read_locked(self, reader):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._with_lock() as lock_file:
            self._lock(lock_file)
            try:
                self._load()
                return reader()
            finally:
                self._unlock(lock_file)

    def _mutate_locked(self, mutation) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._with_lock() as lock_file:
            self._lock(lock_file)
            try:
                self._load()
                mutation()
                self._save()
            finally:
                self._unlock(lock_file)

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)

        def mutation() -> None:
            previous = self._records.get(record.request_id)
            if previous is None:
                if record.state is not ExecutionLifecycleState.PENDING:
                    raise ValueError("novo ciclo deve iniciar em PENDING.")
            elif previous.state is ExecutionLifecycleState.UNKNOWN:
                if record.state is not ExecutionLifecycleState.UNKNOWN:
                    raise ValueError("execução UNKNOWN requer reconciliação explícita.")
            elif previous.state in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
                raise ValueError("estado terminal não pode ser alterado.")
            elif previous.state is ExecutionLifecycleState.PENDING and record.state not in (
                ExecutionLifecycleState.PENDING,
                ExecutionLifecycleState.ACCEPTED,
                ExecutionLifecycleState.REJECTED,
                ExecutionLifecycleState.UNKNOWN,
            ):
                raise ValueError("transição de PENDING inválida.")
            if previous is not None and record.updated_at < previous.updated_at:
                raise ValueError("updated_at não pode retroceder.")
            self._records[record.request_id] = record

        self._mutate_locked(mutation)

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        return self._read_locked(lambda: self._records.get(request_id))

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        if not isinstance(updated_at, datetime):
            raise ValueError("timestamp inválido.")

        result: ExecutionLifecycleRecord | None = None

        def mutation() -> None:
            nonlocal result
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state is not ExecutionLifecycleState.UNKNOWN:
                raise ValueError("reconciliação exige estado UNKNOWN.")
            if updated_at < current.updated_at:
                raise ValueError("updated_at da reconciliação não pode retroceder.")
            result = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._validate(result)
            self._records[request_id] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def reconcile_missing(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "", capability: object = None) -> ExecutionLifecycleRecord:
        """Create the terminal Lifecycle record for a Ledger-only crash window.

        This is permitted only when the Ledger has already been independently
        reconciled. It never creates a dispatchable PENDING state.
        """
        if capability is not LIFECYCLE_RECOVERY_CAPABILITY:
            raise ValueError("reconciliação ausente exige capacidade interna de recovery.")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação ausente exige estado ACCEPTED ou REJECTED.")
        if not isinstance(updated_at, datetime):
            raise ValueError("timestamp inválido.")
        result: ExecutionLifecycleRecord | None = None

        def mutation() -> None:
            nonlocal result
            if request_id in self._records:
                raise ValueError("execução já possui registro de Lifecycle.")
            result = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._validate(result)
            self._records[request_id] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def reconcile_pending(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        """Close the Ledger-terminal -> Lifecycle-PENDING crash window.

        This is intentionally separate from reconcile(): callers must prove the
        Ledger transition first and the REAL gateway holds the shared
        execution coordination lock while performing both mutations.
        """
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação PENDING exige estado ACCEPTED ou REJECTED.")
        if not isinstance(updated_at, datetime):
            raise ValueError("timestamp inválido.")
        result: ExecutionLifecycleRecord | None = None

        def mutation() -> None:
            nonlocal result
            current = self._records.get(request_id)
            if current is None:
                raise ValueError("execução não encontrada.")
            if current.state is not ExecutionLifecycleState.PENDING:
                raise ValueError("reconciliação PENDING exige estado PENDING.")
            if updated_at < current.updated_at:
                raise ValueError("updated_at da reconciliação PENDING não pode retroceder.")
            result = ExecutionLifecycleRecord(request_id, state, updated_at, message)
            self._validate(result)
            self._records[request_id] = result

        self._mutate_locked(mutation)
        assert result is not None
        return result

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        return self._read_locked(lambda: tuple(self._records[key] for key in sorted(self._records)))
