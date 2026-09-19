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

    @classmethod
    def from_path(cls, path: str | Path, *, kill_switch: KillSwitch | None = None, safety_path: str | Path | None = None) -> "PersistentOperationalRecorder":
        store = OperationMemoryStore(path)
        safety_store = OperationalSafetyStore(safety_path or f"{path}.safety.json")
        audit, persisted_kill_switch = safety_store.load()
        if kill_switch is not None:
            if persisted_kill_switch.state.enabled and not kill_switch.state.enabled:
                kill_switch.activate(persisted_kill_switch.state.reason or "estado persistido")
            active_kill_switch = kill_switch
        else:
            active_kill_switch = persisted_kill_switch
        recorder = P4OperationalRecorder(audit=audit, memory=store.load(), kill_switch=active_kill_switch)
        return cls(store=store, safety_store=safety_store, recorder=recorder)

    def _reload_safety(self) -> None:
        if self.safety_store is None:
            return
        audit, kill_switch = self.safety_store.load()
        self.recorder.audit = audit
        # Reloading durable state is a recovery operation. It may restore a
        # persisted emergency stop, but it must never clear a live stop merely
        # because the durable snapshot says disabled. Explicit deactivation
        # already goes through deactivate_kill_switch(), which persists first.
        if kill_switch.state.enabled:
            self.recorder.kill_switch.activate(kill_switch.state.reason or "estado persistido")

    def _reload_memory(self) -> None:
        self.recorder.memory = self.store.load()

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
        try:
            if self.safety_store is not None:
                self.safety_store.append_audit(record)
        except Exception:
            try:
                self._reload_safety()
            except Exception:
                pass
            raise
        return record

    def record_operation(self, snapshot: DecisionSnapshot, *, timestamp: datetime, result: str = "PENDENTE", entry_conditions: tuple[str, ...] = (), audit_record: DecisionAuditRecord | None = None) -> RecordedOperation:
        recorded = self.recorder.record_operation(
            snapshot,
            timestamp=timestamp,
            result=result,
            entry_conditions=entry_conditions,
            audit_record=audit_record,
        )
        try:
            if self.safety_store is not None:
                self.safety_store.append_audit(recorded.audit)
        except Exception:
            try:
                self._reload_memory()
            except Exception:
                pass
            if self.safety_store is not None:
                try:
                    self._reload_safety()
                except Exception:
                    pass
            raise
        try:
            self.store.append(recorded.memory)
        except Exception:
            # The audit may already be durable. Rebuild both views from disk;
            # recovery/audit inspection must see the durable truth rather than
            # the speculative in-memory operation. Never mask the original
            # persistence exception if a best-effort reload also fails.
            try:
                self._reload_memory()
            except Exception:
                pass
            if self.safety_store is not None:
                try:
                    self._reload_safety()
                except Exception:
                    pass
            raise
        # The durable writes above are the commit point. A post-commit reload
        # must not turn a successful operation into an apparent failure.
        try:
            self._reload_memory()
            self._reload_safety()
        except Exception:
            # Keep the already-committed operation result available in memory;
            # recovery/reload can be retried by the caller without duplicating
            # the durable append.
            pass
        return recorded

    def settle_operation(self, record: OperationMemoryRecord, result: str) -> OperationMemoryRecord:
        updated = self.store.settle(record, result)
        try:
            self._reload_memory()
        except Exception:
            # Settlement is already durable; do not turn a post-commit
            # refresh failure into a false negative for the caller.
            pass
        return updated

    def can_execute(self) -> bool:
        return self.recorder.can_execute()

    def guard_execution(self) -> None:
        self.recorder.guard_execution()

    def activate_kill_switch(self, reason: str):
        # Persist the safety stop before mutating the live switch. This closes
        # the crash window where the process could activate the switch, fail
        # to persist it, then restart with a durable CLEAR state.
        candidate = KillSwitch()
        candidate.activate(reason)
        if self.safety_store is not None:
            self.safety_store.save_kill_switch(candidate)
        return self.kill_switch.activate(reason)

    def deactivate_kill_switch(self):
        # Fail closed: persist the disabled state before mutating the live
        # kill switch. If durability fails, the live switch remains enabled.
        candidate = KillSwitch()
        candidate.deactivate()
        if self.safety_store is not None:
            self.safety_store.save_kill_switch(candidate)
        state = self.kill_switch.deactivate()
        return state
