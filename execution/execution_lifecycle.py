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
                if record.request_id in self._records:
                    raise ValueError("request_id duplicado no ciclo de execução persistido.")
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