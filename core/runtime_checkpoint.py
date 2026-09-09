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
    """Persists the last safe runtime checkpoint for restart/recovery."""

    def __init__(self, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        self.path = Path(path)

    def save(self, checkpoint: RuntimeCheckpoint) -> None:
        if not isinstance(checkpoint, RuntimeCheckpoint):
            raise TypeError("checkpoint inválido.")
        if not checkpoint.session_id.strip() or checkpoint.last_cycle < 0:
            raise ValueError("checkpoint inválido.")
        if checkpoint.last_request_id is not None and not checkpoint.last_request_id.strip():
            raise ValueError("request_id do checkpoint inválido.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "session_id": checkpoint.session_id,
            "last_cycle": checkpoint.last_cycle,
            "last_request_id": checkpoint.last_request_id,
            "updated_at": checkpoint.updated_at.isoformat(),
        }, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def load(self) -> RuntimeCheckpoint | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            checkpoint = RuntimeCheckpoint(
                session_id=str(data["session_id"]),
                last_cycle=int(data["last_cycle"]),
                last_request_id=data.get("last_request_id"),
                updated_at=datetime.fromisoformat(str(data["updated_at"])),
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("checkpoint de runtime inválido.") from exc
        if not checkpoint.session_id.strip() or checkpoint.last_cycle < 0:
            raise ValueError("checkpoint de runtime inválido.")
        if checkpoint.last_request_id is not None and not checkpoint.last_request_id.strip():
            raise ValueError("checkpoint de runtime inválido.")
        return checkpoint
