from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "session_id": checkpoint.session_id,
                    "last_cycle": checkpoint.last_cycle,
                    "last_request_id": checkpoint.last_request_id,
                    "updated_at": checkpoint.updated_at.isoformat(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def load(self) -> RuntimeCheckpoint | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
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
