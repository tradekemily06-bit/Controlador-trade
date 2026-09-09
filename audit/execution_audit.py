from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.operational_safety_store import OperationalSafetyStore
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

    def as_dict(self) -> dict[str, object]:
        return {"request_id": self.request_id, "state": self.state.value, "timestamp": self.timestamp.isoformat(), "message": self.message}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ExecutionAuditEvent":
        if not isinstance(data, dict):
            raise ValueError("evento de auditoria inválido.")
        try:
            return cls(
                request_id=str(data["request_id"]),
                state=ExecutionLifecycleState(str(data["state"])),
                timestamp=datetime.fromisoformat(str(data["timestamp"])),
                message=str(data["message"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("evento de auditoria persistido inválido.") from exc


class ExecutionAuditLog:
    """Immutable execution-audit view backed by the existing safety store when provided."""

    def __init__(self, safety_store: OperationalSafetyStore | None = None) -> None:
        if safety_store is not None and not isinstance(safety_store, OperationalSafetyStore):
            raise TypeError("safety_store inválido.")
        self.safety_store = safety_store
        self._events: list[ExecutionAuditEvent] = []
        if self.safety_store is not None:
            self._events = [ExecutionAuditEvent.from_dict(item) for item in self.safety_store.load_execution_audit()]

    def append(self, event: ExecutionAuditEvent) -> None:
        if not isinstance(event, ExecutionAuditEvent):
            raise ValueError("evento de auditoria inválido.")
        if self._events and event.timestamp < self._events[-1].timestamp:
            raise ValueError("eventos de auditoria devem ser cronológicos.")
        self._events.append(event)
        if self.safety_store is not None:
            self.safety_store.save_execution_audit(tuple(item.as_dict() for item in self._events))

    def events(self) -> tuple[ExecutionAuditEvent, ...]:
        return tuple(self._events)

    def for_request(self, request_id: str) -> tuple[ExecutionAuditEvent, ...]:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id é obrigatório.")
        return tuple(event for event in self._events if event.request_id == request_id)
