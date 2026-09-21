from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .decision_audit import DecisionAuditRecord
from .decision_snapshot import DecisionSnapshot
from .kill_switch import KillSwitch
from .operation_memory import OperationMemoryRecord
from .operation_memory_store import OperationMemoryStore
from .operational_safety_store import OperationalSafetyStore
from .p4_operational_recorder import P4OperationalRecorder, RecordedOperation


class PersistentOperationalRecorder:
    """Durable P4 recorder for memory, audit and kill-switch state."""

    def __init__(self, *, store: OperationMemoryStore, safety_store: OperationalSafetyStore | None = None, recorder: P4OperationalRecorder | None = None) -> None:
        if not isinstance(store, OperationMemoryStore):
            raise TypeError("store deve ser OperationMemoryStore.")
        if safety_store is not None and not isinstance(safety_store, OperationalSafetyStore):
            raise TypeError("safety_store deve ser OperationalSafetyStore.")
        self.store = store
        self.safety_store = safety_store
        self.recorder = recorder or P4OperationalRecorder(memory=store.load())
        if self.safety_store is not None:
            # The persisted safety store is the canonical fence for kill-switch
            # changes. This prevents a writer from persisting "enabled" and
            # releasing the fence before the in-memory execution gate adopts it.
            self.kill_switch.set_change_fence(self.safety_store.coordination_lock)

    @classmethod
    def from_path(cls, path: str | Path, *, kill_switch: KillSwitch | None = None, safety_path: str | Path | None = None) -> "PersistentOperationalRecorder":
        store = OperationMemoryStore(path)
        safety_store = OperationalSafetyStore(safety_path or f"{path}.safety.json")
        # Bootstrap is one atomic safety observation: read persisted state and
        # adopt it while holding the same canonical fence used by dispatch.
        with safety_store.coordination_lock():
            audit, persisted_kill_switch = safety_store.load()
            if kill_switch is not None:
                kill_switch.set_change_fence(safety_store.coordination_lock)
                active_kill_switch = kill_switch
            else:
                active_kill_switch = KillSwitch(change_fence=safety_store.coordination_lock)
            active_kill_switch.synchronize_under_change_fence(persisted_kill_switch)
        recorder = P4OperationalRecorder(audit=audit, memory=store.load(), kill_switch=active_kill_switch)
        return cls(store=store, safety_store=safety_store, recorder=recorder)

    def _persist_safety(self) -> None:
        if self.safety_store is not None:
            self.safety_store.save(self.audit, self.kill_switch)

    @property
    def memory(self):
        return self.recorder.memory

    @property
    def audit(self):
        return self.recorder.audit

    @property
    def kill_switch(self):
        return self.recorder.kill_switch

    def record_decision(self, snapshot: DecisionSnapshot, *, timestamp: datetime) -> DecisionAuditRecord:
        record = self.recorder.record_decision(snapshot, timestamp=timestamp)
        self._persist_safety()
        return record

    def record_operation(self, snapshot: DecisionSnapshot, *, timestamp: datetime, result: str = "PENDENTE", entry_conditions: tuple[str, ...] = (), audit_record: DecisionAuditRecord | None = None) -> RecordedOperation:
        recorded = self.recorder.record_operation(snapshot, timestamp=timestamp, result=result, entry_conditions=entry_conditions, audit_record=audit_record)
        self.store.save(self.memory)
        self._persist_safety()
        return recorded

    def settle_operation(self, record: OperationMemoryRecord, result: str) -> OperationMemoryRecord:
        updated = self.recorder.settle_operation(record, result)
        self.store.save(self.memory)
        self._persist_safety()
        return updated

    def can_execute(self) -> bool:
        return self.recorder.can_execute()

    def guard_execution(self) -> None:
        self.recorder.guard_execution()

    def activate_kill_switch(self, reason: str):
        if self.safety_store is None:
            return self.kill_switch.activate(reason)
        # Persisting the durable block and publishing it to the in-memory
        # gate are one critical section. No dispatch can observe the old
        # in-memory state between these two operations.
        with self.safety_store.coordination_lock():
            persisted = self.safety_store.set_kill_switch_under_coordination_fence(enabled=True, reason=reason)
            self.kill_switch.synchronize_under_change_fence(persisted)
            return persisted

    def deactivate_kill_switch(self):
        if self.safety_store is None:
            return self.kill_switch.deactivate()
        # Keep the same atomic boundary for deactivation. A stale "enabled"
        # state is conservative; atomicity nevertheless prevents split-brain
        # safety state and makes recovery deterministic.
        with self.safety_store.coordination_lock():
            persisted = self.safety_store.set_kill_switch_under_coordination_fence(enabled=False)
            self.kill_switch.synchronize_under_change_fence(persisted)
            return persisted
