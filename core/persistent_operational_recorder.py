from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .decision_audit import DecisionAuditRecord
from .decision_snapshot import DecisionSnapshot
from .kill_switch import KillSwitch
from .operation_memory import OperationMemoryRecord
from .operation_memory_store import OperationMemoryStore
from .p4_operational_recorder import P4OperationalRecorder, RecordedOperation


class PersistentOperationalRecorder:
    """Adds durable operation-memory persistence to the validated P4 recorder."""

    def __init__(
        self,
        *,
        store: OperationMemoryStore,
        recorder: P4OperationalRecorder | None = None,
    ) -> None:
        if not isinstance(store, OperationMemoryStore):
            raise TypeError("store deve ser OperationMemoryStore.")
        self.store = store
        self.recorder = recorder or P4OperationalRecorder(memory=store.load())

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        kill_switch: KillSwitch | None = None,
    ) -> "PersistentOperationalRecorder":
        store = OperationMemoryStore(path)
        recorder = P4OperationalRecorder(
            memory=store.load(),
            kill_switch=kill_switch,
        )
        return cls(store=store, recorder=recorder)

    @property
    def memory(self):
        return self.recorder.memory

    @property
    def audit(self):
        return self.recorder.audit

    @property
    def kill_switch(self):
        return self.recorder.kill_switch

    def record_decision(
        self,
        snapshot: DecisionSnapshot,
        *,
        timestamp: datetime,
    ) -> DecisionAuditRecord:
        """Record an audit event without creating a memory entry."""
        return self.recorder.record_decision(snapshot, timestamp=timestamp)

    def record_operation(
        self,
        snapshot: DecisionSnapshot,
        *,
        timestamp: datetime,
        result: str = "PENDENTE",
        entry_conditions: tuple[str, ...] = (),
        audit_record: DecisionAuditRecord | None = None,
    ) -> RecordedOperation:
        recorded = self.recorder.record_operation(
            snapshot,
            timestamp=timestamp,
            result=result,
            entry_conditions=entry_conditions,
            audit_record=audit_record,
        )
        self.store.save(self.memory)
        return recorded

    def settle_operation(
        self,
        record: OperationMemoryRecord,
        result: str,
    ) -> OperationMemoryRecord:
        updated = self.recorder.settle_operation(record, result)
        self.store.save(self.memory)
        return updated

    def can_execute(self) -> bool:
        return self.recorder.can_execute()

    def guard_execution(self) -> None:
        self.recorder.guard_execution()
