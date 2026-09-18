from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.durable_json import atomic_write_json, locked_path, read_json


@dataclass(frozen=True)
class RuntimeCheckpoint:
    session_id: str
    last_cycle: int
    last_request_id: str | None
    updated_at: datetime


class RuntimeCheckpointStore:
    """Durable checkpoint for safe runtime recovery; never replays an order."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)

    def save(self, checkpoint: RuntimeCheckpoint) -> None:
        self._validate(checkpoint)
        payload = {
            "session_id": checkpoint.session_id,
            "last_cycle": checkpoint.last_cycle,
            "last_request_id": checkpoint.last_request_id,
            "updated_at": checkpoint.updated_at.isoformat(),
        }
        with locked_path(self.path):
            # A stale runtime instance must never move the durable checkpoint
            # backwards. Corrupt durable state must fail closed rather than
            # being silently replaced by a fresh checkpoint.
            if self.path.exists():
                try:
                    current = read_json(self.path, {})
                    if not isinstance(current, dict):
                        raise ValueError("checkpoint de runtime inválido.")
                    current_checkpoint = RuntimeCheckpoint(
                        session_id=current["session_id"],
                        last_cycle=current["last_cycle"],
                        last_request_id=current.get("last_request_id"),
                        updated_at=datetime.fromisoformat(current["updated_at"]),
                    )
                    self._validate(current_checkpoint)
                except ValueError as exc:
                    if str(exc) == "checkpoint de runtime inválido.":
                        raise
                    raise ValueError("checkpoint de runtime inválido.") from exc
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ValueError("checkpoint de runtime inválido.") from exc

                current_aware = (
                    current_checkpoint.updated_at.tzinfo is not None
                    and current_checkpoint.updated_at.utcoffset() is not None
                )
                incoming_aware = (
                    checkpoint.updated_at.tzinfo is not None
                    and checkpoint.updated_at.utcoffset() is not None
                )
                if current_aware != incoming_aware:
                    raise ValueError("timestamps de checkpoint devem usar o mesmo regime de timezone.")

                same_session_regression = (
                    current_checkpoint.session_id == checkpoint.session_id
                    and checkpoint.last_cycle < current_checkpoint.last_cycle
                )
                older_snapshot = checkpoint.updated_at < current_checkpoint.updated_at
                same_timestamp_conflict = (
                    checkpoint.updated_at == current_checkpoint.updated_at
                    and checkpoint != current_checkpoint
                )
                if same_session_regression or older_snapshot or same_timestamp_conflict:
                    return
            atomic_write_json(self.path, payload)

    def load(self) -> RuntimeCheckpoint | None:
        try:
            with locked_path(self.path):
                if not self.path.exists():
                    return None
                data = read_json(self.path, {})
            if not isinstance(data, dict):
                raise ValueError
            checkpoint = RuntimeCheckpoint(
                session_id=data["session_id"],
                last_cycle=data["last_cycle"],
                last_request_id=data.get("last_request_id"),
                updated_at=datetime.fromisoformat(data["updated_at"]),
            )
            self._validate(checkpoint)
            return checkpoint
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("checkpoint de runtime inválido.") from exc

    @staticmethod
    def _validate(checkpoint: RuntimeCheckpoint) -> None:
        if not isinstance(checkpoint, RuntimeCheckpoint):
            raise ValueError("checkpoint inválido.")
        if not isinstance(checkpoint.session_id, str) or not checkpoint.session_id.strip():
            raise ValueError("checkpoint inválido.")
        if not isinstance(checkpoint.last_cycle, int) or isinstance(checkpoint.last_cycle, bool) or checkpoint.last_cycle < 0:
            raise ValueError("checkpoint inválido.")
        if checkpoint.last_request_id is not None and (
            not isinstance(checkpoint.last_request_id, str) or not checkpoint.last_request_id.strip()
        ):
            raise ValueError("request_id do checkpoint inválido.")
        if not isinstance(checkpoint.updated_at, datetime):
            raise ValueError("checkpoint inválido.")
