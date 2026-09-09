from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from execution.execution_lifecycle import ExecutionLifecycleState


@dataclass(frozen=True)
class ExecutionAuditEvent:
    request_id: str
    state: ExecutionLifecycleState
    timestamp: datetime
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id é obrigatório.")
        if not isinstance(self.state, ExecutionLifecycleState):
            raise ValueError("estado inválido.")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp inválido.")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message é obrigatório.")


class ExecutionAuditLog:
    """In-memory immutable-event view; recording an event has no execution side effect."""

    def __init__(self) -> None:
        self._events: list[ExecutionAuditEvent] = []

    def append(self, event: ExecutionAuditEvent) -> None:
        if not isinstance(event, ExecutionAuditEvent):
            raise ValueError("evento de auditoria inválido.")
        self._events.append(event)

    def events(self) -> tuple[ExecutionAuditEvent, ...]:
        return tuple(self._events)

    def for_request(self, request_id: str) -> tuple[ExecutionAuditEvent, ...]:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id é obrigatório.")
        return tuple(event for event in self._events if event.request_id == request_id)
