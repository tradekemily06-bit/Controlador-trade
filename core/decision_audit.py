from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .decision_snapshot import DecisionSnapshot


class AuditValidationError(ValueError):
    """Raised when an audit event is incomplete or invalid."""


@dataclass(frozen=True)
class DecisionAuditRecord:
    """Immutable audit event captured before operational memory."""

    timestamp: datetime
    snapshot: DecisionSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise AuditValidationError("timestamp deve ser datetime.")
        if not isinstance(self.snapshot, DecisionSnapshot):
            raise AuditValidationError("snapshot inválido.")

    def as_dict(self) -> dict[str, Any]:
        data = self.snapshot.as_dict()
        data["timestamp"] = self.timestamp.isoformat()
        return data


class DecisionAudit:
    """In-memory append-only audit trail with validated immutable records."""

    def __init__(self) -> None:
        self._records: list[DecisionAuditRecord] = []

    def append(self, record: DecisionAuditRecord) -> None:
        if not isinstance(record, DecisionAuditRecord):
            raise TypeError("record deve ser DecisionAuditRecord.")
        if self._records and record.timestamp < self._records[-1].timestamp:
            raise AuditValidationError("eventos de auditoria devem ser cronológicos.")
        self._records.append(record)

    def records(self) -> tuple[DecisionAuditRecord, ...]:
        return tuple(self._records)

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self._records),
            "executar": sum(r.snapshot.decision == "EXECUTAR" for r in self._records),
            "bloquear": sum(r.snapshot.decision == "BLOQUEAR" for r in self._records),
            "aguardar": sum(r.snapshot.decision == "AGUARDAR" for r in self._records),
            "compra": sum(r.snapshot.signal == "COMPRA" for r in self._records),
            "venda": sum(r.snapshot.signal == "VENDA" for r in self._records),
        }
