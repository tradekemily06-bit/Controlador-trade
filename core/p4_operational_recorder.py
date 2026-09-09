from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .decision_audit import DecisionAudit, DecisionAuditRecord
from .decision_snapshot import DecisionSnapshot
from .kill_switch import KillSwitch
from .models import Signal
from .operation_memory import OperationMemory, OperationMemoryRecord


class OperationalRecorderError(ValueError):
    """Raised when the P4 operational recording flow is invalid."""


@dataclass(frozen=True)
class RecordedOperation:
    """Links an audited decision to its operational memory record."""

    audit: DecisionAuditRecord
    memory: OperationMemoryRecord


class P4OperationalRecorder:
    """Coordinates P4 safety, audit and memory without changing strategy logic."""

    def __init__(
        self,
        *,
        audit: DecisionAudit | None = None,
        memory: OperationMemory | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        self.audit = audit or DecisionAudit()
        self.memory = memory or OperationMemory()
        self.kill_switch = kill_switch or KillSwitch()

    def record_decision(
        self, snapshot: DecisionSnapshot, *, timestamp: datetime
    ) -> DecisionAuditRecord:
        """Record the immutable audit event before any memory entry is created."""
        record = DecisionAuditRecord(timestamp=timestamp, snapshot=snapshot)
        self.audit.append(record)
        return record

    def record_operation(
        self,
        snapshot: DecisionSnapshot,
        *,
        timestamp: datetime,
        result: str = "PENDENTE",
        entry_conditions: tuple[str, ...] = (),
        audit_record: DecisionAuditRecord | None = None,
    ) -> RecordedOperation:
        """Audit first, then persist memory; reuse an existing audit when supplied."""
        if audit_record is None:
            audit_record = self.record_decision(snapshot, timestamp=timestamp)
        elif audit_record.snapshot != snapshot:
            raise OperationalRecorderError(
                "audit_record não corresponde ao snapshot da operação."
            )

        memory_record = OperationMemoryRecord(
            timestamp=timestamp,
            signal=Signal(snapshot.signal),
            score=snapshot.analysis_score,
            decision=snapshot.decision,
            reason=snapshot.decision_reason,
            result=result,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            quality_score=snapshot.quality_score,
            quality_level=snapshot.quality_level,
            entry_conditions=entry_conditions,
        )
        self.memory.append(memory_record)
        return RecordedOperation(audit=audit_record, memory=memory_record)

    def settle_operation(
        self, record: OperationMemoryRecord, result: str
    ) -> OperationMemoryRecord:
        """Settle an existing memory entry without creating a duplicate event."""
        return self.memory.settle(record, result)

    def can_execute(self) -> bool:
        """Return the final P4 safety gate state."""
        return self.kill_switch.allows_execution()

    def guard_execution(self) -> None:
        """Raise before execution when the independent kill switch is active."""
        self.kill_switch.guard()
