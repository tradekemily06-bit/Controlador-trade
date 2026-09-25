from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .decision_audit import DecisionAuditRecord
from .decision_snapshot import DecisionSnapshot
from .kill_switch import KillSwitch
from .models import Signal
from .operation_memory import OperationMemoryRecord
from .operation_memory_store import OperationMemoryStore
from .operational_safety_store import OperationalSafetyStore
from .p4_operational_recorder import P4OperationalRecorder, RecordedOperation


class PersistentOperationalRecorder:
    """Durable P4 recorder with atomic cross-process mutations."""

    def __init__(
        self,
        *,
        store: OperationMemoryStore,
        safety_store: OperationalSafetyStore | None = None,
        recorder: P4OperationalRecorder | None = None,
    ) -> None:
        if not isinstance(store, OperationMemoryStore):
            raise TypeError("store deve ser OperationMemoryStore.")
        if safety_store is not None and not isinstance(safety_store, OperationalSafetyStore):
            raise TypeError("safety_store deve ser OperationalSafetyStore.")
        self.store = store
        self.safety_store = safety_store
        self.recorder = recorder or P4OperationalRecorder(memory=store.load())

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        kill_switch: KillSwitch | None = None,
        safety_path: str | Path | None = None,
    ) -> "PersistentOperationalRecorder":
        store = OperationMemoryStore(path)
        safety_store = OperationalSafetyStore(safety_path or f"{path}.safety.json")
        audit, persisted_kill_switch = safety_store.load()
        if kill_switch is not None:
            if persisted_kill_switch.state.enabled and not kill_switch.state.enabled:
                kill_switch.activate(persisted_kill_switch.state.reason or "estado persistido")
            active_kill_switch = kill_switch
        else:
            active_kill_switch = persisted_kill_switch
        recorder = P4OperationalRecorder(
            audit=audit,
            memory=store.load(),
            kill_switch=active_kill_switch,
        )
        return cls(store=store, safety_store=safety_store, recorder=recorder)

    @property
    def memory(self):
        return self.recorder.memory

    @property
    def audit(self):
        return self.recorder.audit

    @property
    def kill_switch(self):
        return self.recorder.kill_switch

    def _refresh_memory(self) -> None:
        self.recorder.memory = self.store.load()

    def _refresh_audit(self) -> None:
        if self.safety_store is None:
            return
        audit, _ = self.safety_store.load()
        self.recorder.audit = audit

    def record_decision(
        self,
        snapshot: DecisionSnapshot,
        *,
        timestamp: datetime,
    ) -> DecisionAuditRecord:
        record = DecisionAuditRecord(timestamp=timestamp, snapshot=snapshot)
        if self.safety_store is not None:
            persisted = self.safety_store.append_audit(record)
            self.recorder.audit = type(self.recorder.audit)()
            for item in persisted:
                self.recorder.audit.append(item)
        else:
            self.recorder.audit.append(record)
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
        if audit_record is None:
            audit_record = self.record_decision(snapshot, timestamp=timestamp)
        elif audit_record.snapshot != snapshot:
            raise ValueError("audit_record não corresponde ao snapshot da operação.")
        elif self.safety_store is not None and audit_record not in self.audit.records():
            self.record_decision(snapshot, timestamp=audit_record.timestamp)

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
        memory = self.store.append(memory_record)
        self.recorder.memory = memory
        return RecordedOperation(audit=audit_record, memory=memory_record)

    def settle_operation(
        self,
        record: OperationMemoryRecord,
        result: str,
    ) -> OperationMemoryRecord:
        memory = self.store.settle(record, result)
        self.recorder.memory = memory
        return next(
            item for item in memory.records()
            if item.timestamp == record.timestamp
            and item.symbol == record.symbol
            and item.timeframe == record.timeframe
            and item.signal is record.signal
            and item.score == record.score
            and item.decision == record.decision
            and item.reason == record.reason
            and item.result == result
        )

    def can_execute(self) -> bool:
        return self.recorder.can_execute()

    def guard_execution(self) -> None:
        self.recorder.guard_execution()

    def activate_kill_switch(self, reason: str):
        state = self.kill_switch.activate(reason)
        if self.safety_store is not None:
            self.safety_store.set_kill_switch(self.kill_switch)
        return state

    def deactivate_kill_switch(self):
        if self.safety_store is not None:
            _, persisted_kill_switch = self.safety_store.load()
            state = persisted_kill_switch.deactivate()
            self.recorder.kill_switch = persisted_kill_switch
            self.safety_store.set_kill_switch(persisted_kill_switch)
            return state
        return self.kill_switch.deactivate()
