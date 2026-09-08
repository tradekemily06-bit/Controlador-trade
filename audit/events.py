from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class AuditEventType(str, Enum):
    ANALYSIS = "ANALYSIS"
    DECISION = "DECISION"
    RISK = "RISK"
    EXECUTION = "EXECUTION"
    ERROR = "ERROR"


@dataclass(frozen=True)
class AuditEvent:
    event_type: AuditEventType
    message: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("message não pode ser vazio.")

        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp deve possuir timezone.")

        if not isinstance(self.data, Mapping):
            raise TypeError("data deve ser um Mapping.")


class AuditLogger:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def clear(self) -> None:
        self._events.clear()
