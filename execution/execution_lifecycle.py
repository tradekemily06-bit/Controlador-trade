from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime

from core.durable_json import atomic_write_json, locked_path, read_json


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


class ExecutionLifecycleStore:
    """Durable execution state; UNKNOWN is terminal until explicitly reconciled."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)
        self._records: dict[str, ExecutionLifecycleRecord] = {}
        self._load()

    def _load_unlocked(self) -> None:
        self._records = {}
        if not self.path.exists():
            return
        try:
            payload = read_json(self.path, [])
            if not isinstance(payload, list):
                raise ValueError
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
                self._records[record.request_id] = record
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    def _load(self) -> None:
        try:
            with locked_path(self.path):
                self._load_unlocked()
        except ValueError:
            raise
        except OSError as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    @staticmethod
    def _validate(record: ExecutionLifecycleRecord) -> None:
        if not isinstance(record.request_id, str) or not record.request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(record.state, ExecutionLifecycleState):
            raise ValueError("estado de execução inválido.")
        if not isinstance(record.updated_at, datetime):
            raise ValueError("timestamp inválido.")
        if not isinstance(record.message, str):
            raise ValueError("mensagem inválida.")

    def put(self, record: ExecutionLifecycleRecord) -> None:
        self._validate(record)
        try:
            with locked_path(self.path):
                self._load_unlocked()
                previous = self._records.get(record.request_id)
                if previous is not None:
                    if previous.state is ExecutionLifecycleState.UNKNOWN and record.state is not ExecutionLifecycleState.UNKNOWN:
                        raise ValueError("execução UNKNOWN requer reconciliação explícita.")
                    if previous.state in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED) and record.state is not previous.state:
                        raise ValueError("estado terminal não pode ser alterado sem reconciliação explícita.")
                self._records[record.request_id] = record
                self._save_unlocked()
        except ValueError:
            raise
        except OSError as exc:
            raise OSError("não foi possível persistir o ciclo de execução.") from exc

    def get(self, request_id: str) -> ExecutionLifecycleRecord | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id não pode ser vazio.")
        try:
            with locked_path(self.path):
                self._load_unlocked()
                return self._records.get(request_id)
        except ValueError:
            raise
        except OSError as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    def reconcile(self, request_id: str, state: ExecutionLifecycleState, *, updated_at: datetime, message: str = "") -> ExecutionLifecycleRecord:
        if state not in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED):
            raise ValueError("reconciliação exige estado ACCEPTED ou REJECTED.")
        try:
            with locked_path(self.path):
                self._load_unlocked()
                current = self._records.get(request_id)
                if current is None:
                    raise ValueError("execução não encontrada.")
                record = ExecutionLifecycleRecord(request_id, state, updated_at, message)
                self._validate(record)
                self._records[request_id] = record
                self._save_unlocked()
                return record
        except ValueError:
            raise
        except OSError as exc:
            raise OSError("não foi possível persistir a reconciliação.") from exc

    def records(self) -> tuple[ExecutionLifecycleRecord, ...]:
        try:
            with locked_path(self.path):
                self._load_unlocked()
                return tuple(self._records[key] for key in sorted(self._records))
        except ValueError:
            raise
        except OSError as exc:
            raise ValueError("ciclo de execução persistido inválido.") from exc

    def _save_unlocked(self) -> None:
        payload = [
            {
                "request_id": r.request_id,
                "state": r.state.value,
                "updated_at": r.updated_at.isoformat(),
                "message": r.message,
            }
            for r in self.records_unlocked()
        ]
        atomic_write_json(self.path, payload)

    def records_unlocked(self) -> tuple[ExecutionLifecycleRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))
