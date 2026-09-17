from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from core.observability_redaction import redact, redact_text


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
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message não pode ser vazio.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp deve possuir timezone.")
        if not isinstance(self.data, Mapping):
            raise TypeError("data deve ser um Mapping.")
        object.__setattr__(self, "message", redact_text(self.message.strip()))
        object.__setattr__(self, "data", redact(self.data))


class AuditLogger:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        if not isinstance(event, AuditEvent):
            raise TypeError("event deve ser um AuditEvent.")
        self._events.append(event)

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def clear(self) -> None:
        self._events.clear()
