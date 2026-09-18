from datetime import datetime, timezone
from threading import Thread

import pytest

from core.decision_audit import DecisionAudit, DecisionAuditRecord
from core.decision_snapshot import DecisionSnapshot
from core.durable_json import atomic_write_json
from core.kill_switch import KillSwitch
from core.operation_memory import OperationMemory, OperationMemoryRecord
from core.operation_memory_store import OperationMemoryStore
from core.models import Signal
from core.operational_safety_store import OperationalSafetyStore
from core.persistent_operational_recorder import PersistentOperationalRecorder
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)


def test_atomic_json_write_keeps_previous_state_if_fsync_fails(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"version": 1})

    def fail_fsync(_fd):
        raise OSError("simulated durability failure")

    monkeypatch.setattr("core.durable_json.os.fsync", fail_fsync)

    with pytest.raises(OSError, match="simulated durability failure"):
        atomic_write_json(path, {"version": 2})

    assert path.read_text(encoding="utf-8").strip().startswith("{")
    assert '"version": 1' in path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_atomic_json_write_keeps_previous_state_if_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"version": 1})

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("core.durable_json.os.replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_json(path, {"version": 2})

    assert '"version": 1' in path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_atomic_json_write_directory_fsync_failure_leaves_committed_state_for_recovery(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"version": 1})
    original_fsync = __import__("os").fsync
    calls = {"count": 0}

    def fail_directory_fsync(fd):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated directory durability failure")
        return original_fsync(fd)

    monkeypatch.setattr("core.durable_json.os.fsync", fail_directory_fsync)

    with pytest.raises(OSError, match="simulated directory durability failure"):
        atomic_write_json(path, {"version": 2})

    # os.replace already committed the new file before directory fsync.
    # Recovery/retry must therefore inspect durable state instead of assuming
    # the failed call rolled back to the previous version.
    assert '"version": 2' in path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_lifecycle_concurrent_writers_do_not_lose_records(tmp_path):
    path = tmp_path / "lifecycle.json"
    first = ExecutionLifecycleStore(path)
    second = ExecutionLifecycleStore(path)
    now = datetime.now(timezone.utc)

    errors = []

    def write(store, request_id):
        try:
            store.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.PENDING, now))
        except Exception as exc:  # pragma: no cover - assertion below reports it
            errors.append(exc)

    threads = [
        Thread(target=write, args=(first, "req-a")),
        Thread(target=write, args=(second, "req-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    restored = ExecutionLifecycleStore(path)
    assert {record.request_id for record in restored.records()} == {"req-a", "req-b"}


def test_safety_store_rejects_corrupted_execution_audit_order(tmp_path):
    path = tmp_path / "safety.json"
    atomic_write_json(
        path,
        {
            "audit": [],
            "kill_switch": {},
            "execution_audit": [
                {
                    "request_id": "req-newer",
                    "state": "UNKNOWN",
                    "timestamp": "2026-01-01T00:00:02+00:00",
                    "message": "newer",
                },
                {
                    "request_id": "req-older",
                    "state": "UNKNOWN",
                    "timestamp": "2026-01-01T00:00:01+00:00",
                    "message": "older",
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="cronológica"):
        OperationalSafetyStore(path).load_execution_audit()


def test_safety_store_rejects_corrupted_execution_audit_timezone_regime(tmp_path):
    path = tmp_path / "safety.json"
    atomic_write_json(
        path,
        {
            "audit": [],
            "kill_switch": {},
            "execution_audit": [
                {
                    "request_id": "req-aware",
                    "state": "UNKNOWN",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "message": "aware",
                },
                {
                    "request_id": "req-naive",
                    "state": "UNKNOWN",
                    "timestamp": "2026-01-01T00:00:01",
                    "message": "naive",
                },
            ],
        },
    )

    with pytest.raises(ValueError, match="timezone"):
        OperationalSafetyStore(path).load_execution_audit()


def test_safety_store_concurrent_updates_preserve_execution_audit(tmp_path):
    path = tmp_path / "safety.json"
    store = OperationalSafetyStore(path)
    kill_switch = KillSwitch()
    errors = []

    event = {
        "request_id": "req-safe",
        "state": "UNKNOWN",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "message": "requires reconciliation",
    }

    def save_audit():
        try:
            store.save(DecisionAudit(), kill_switch)
        except Exception as exc:  # pragma: no cover - assertion below reports it
            errors.append(exc)

    def save_execution():
        try:
            store.save_execution_audit((event,))
        except Exception as exc:  # pragma: no cover - assertion below reports it
            errors.append(exc)

    threads = [Thread(target=save_audit), Thread(target=save_execution)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert store.load_execution_audit() == (event,)


def test_checkpoint_uses_durable_atomic_writer(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    store = RuntimeCheckpointStore(path)
    first = RuntimeCheckpoint("s1", 1, "req-1", datetime.now(timezone.utc))
    store.save(first)

    def fail_fsync(_fd):
        raise OSError("simulated durability failure")

    monkeypatch.setattr("core.durable_json.os.fsync", fail_fsync)
    second = RuntimeCheckpoint("s1", 2, "req-2", datetime.now(timezone.utc))

    with pytest.raises(OSError, match="simulated durability failure"):
        store.save(second)

    assert store.load() == first


def test_activate_kill_switch_does_not_open_a_restart_window_on_persistence_failure(tmp_path, monkeypatch):
    from core.persistent_operational_recorder import PersistentOperationalRecorder

    recorder = PersistentOperationalRecorder.from_path(tmp_path / "memory.json")

    def fail_save(*_args, **_kwargs):
        raise OSError("simulated persistence failure")

    monkeypatch.setattr(recorder.safety_store, "save_kill_switch", fail_save)

    with pytest.raises(OSError, match="simulated persistence failure"):
        recorder.activate_kill_switch("safety stop")

    assert recorder.kill_switch.state.enabled is False
    restored = PersistentOperationalRecorder.from_path(
        tmp_path / "memory.json",
        safety_path=tmp_path / "memory.json.safety.json",
    )
    assert restored.kill_switch.state.enabled is False


def test_deactivate_kill_switch_is_fail_closed_on_persistence_failure(tmp_path, monkeypatch):
    from core.persistent_operational_recorder import PersistentOperationalRecorder

    recorder = PersistentOperationalRecorder.from_path(tmp_path / "memory.json")
    recorder.activate_kill_switch("safety stop")

    def fail_save(*_args, **_kwargs):
        raise OSError("simulated persistence failure")

    monkeypatch.setattr(recorder.safety_store, "save_kill_switch", fail_save)

    with pytest.raises(OSError, match="simulated persistence failure"):
        recorder.deactivate_kill_switch()

    assert recorder.kill_switch.state.enabled is True
    assert recorder.kill_switch.state.reason == "safety stop"


def _snapshot(index: int) -> DecisionSnapshot:
    return DecisionSnapshot(
        signal="COMPRA",
        analysis_score=80.0 + index,
        confirmed=True,
        quality_score=90.0,
        quality_level="FORTE",
        actionable=True,
        decision="EXECUTAR",
        decision_reason=f"snapshot-{index}",
        market_context="ALTA",
        market_direction="COMPRA",
        market_score=80.0,
        operational_state_available=True,
        trades_today=index,
        consecutive_losses=0,
        symbol="TEST",
        timeframe="5m",
    )


def test_operation_memory_concurrent_appends_use_latest_durable_snapshot(tmp_path):
    path = tmp_path / "memory.json"
    first = OperationMemoryStore(path)
    second = OperationMemoryStore(path)
    now = datetime.now(timezone.utc)
    records = [
        OperationMemoryRecord(now, signal=Signal.COMPRA, score=80, decision="EXECUTAR", reason="a"),
        OperationMemoryRecord(now, signal=Signal.VENDA, score=81, decision="EXECUTAR", reason="b"),
    ]
    errors = []

    def append(store, record):
        try:
            store.append(record)
        except Exception as exc:  # pragma: no cover - assertion below reports it
            errors.append(exc)

    threads = [
        Thread(target=append, args=(first, records[0])),
        Thread(target=append, args=(second, records[1])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert set(OperationMemoryStore(path).load().records()) == set(records)


def test_safety_audit_concurrent_appends_use_latest_durable_snapshot(tmp_path):
    path = tmp_path / "safety.json"
    first = OperationalSafetyStore(path)
    second = OperationalSafetyStore(path)
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = [DecisionAuditRecord(timestamp, _snapshot(i)) for i in range(2)]
    errors = []

    def append(store, record):
        try:
            store.append_audit(record)
        except Exception as exc:  # pragma: no cover - assertion below reports it
            errors.append(exc)

    threads = [
        Thread(target=append, args=(first, records[0])),
        Thread(target=append, args=(second, records[1])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    restored, _ = OperationalSafetyStore(path).load()
    assert {record.snapshot.decision_reason for record in restored.records()} == {
        record.snapshot.decision_reason for record in records
    }


def test_settle_persists_before_mutating_in_memory_recorder(tmp_path, monkeypatch):
    from core.persistent_operational_recorder import PersistentOperationalRecorder

    path = tmp_path / "memory.json"
    recorder = PersistentOperationalRecorder.from_path(path)
    recorded = recorder.record_operation(_snapshot(0), timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))

    def fail_fsync(_fd):
        raise OSError("simulated durability failure")

    monkeypatch.setattr("core.durable_json.os.fsync", fail_fsync)

    with pytest.raises(OSError, match="simulated durability failure"):
        recorder.settle_operation(recorded.memory, "WIN")

    assert recorder.memory.records() == (recorded.memory,)
    assert OperationMemoryStore(path).load().records() == (recorded.memory,)


def test_kill_switch_update_preserves_audit_from_another_recorder(tmp_path):
    from core.persistent_operational_recorder import PersistentOperationalRecorder

    path = tmp_path / "memory.json"
    safety_path = tmp_path / "safety.json"
    first = PersistentOperationalRecorder.from_path(path, safety_path=safety_path)
    second = PersistentOperationalRecorder.from_path(path, safety_path=safety_path)

    first.record_decision(_snapshot(0), timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second.record_decision(_snapshot(1), timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))

    first.activate_kill_switch("concurrent safety stop")

    restored, kill_switch = OperationalSafetyStore(safety_path).load()
    assert len(restored.records()) == 2
    assert kill_switch.state.enabled is True
    assert kill_switch.state.reason == "concurrent safety stop"


def test_record_operation_does_not_report_failure_after_durable_commit(tmp_path, monkeypatch):
    recorder = PersistentOperationalRecorder.from_path(
        tmp_path / "operations.json",
        safety_path=tmp_path / "safety.json",
    )
    snapshot = _snapshot(0)
    monkeypatch.setattr(recorder, "_reload_memory", lambda: (_ for _ in ()).throw(OSError("reload failed")))
    monkeypatch.setattr(recorder, "_reload_safety", lambda: (_ for _ in ()).throw(OSError("reload failed")))

    recorded = recorder.record_operation(snapshot, timestamp=datetime.now(timezone.utc))

    assert recorded.memory in OperationMemoryStore(tmp_path / "operations.json").load().records()
    assert recorder.audit.records()


def test_settle_operation_durable_commit_is_not_rolled_back_by_reload_failure(tmp_path, monkeypatch):
    path = tmp_path / "operations.json"
    recorder = PersistentOperationalRecorder.from_path(path, safety_path=tmp_path / "safety.json")
    snapshot = _snapshot(0)
    recorded = recorder.record_operation(snapshot, timestamp=datetime.now(timezone.utc))

    monkeypatch.setattr(recorder, "_reload_memory", lambda: (_ for _ in ()).throw(OSError("reload failed")))

    updated = recorder.settle_operation(recorded.memory, "WIN")

    assert OperationMemoryStore(path).load().records()[0].result == "WIN"
    assert updated.result == "WIN"


def test_record_operation_audit_commit_then_memory_failure_reloads_durable_truth(tmp_path, monkeypatch):
    store = OperationMemoryStore(tmp_path / "memory.json")
    safety = OperationalSafetyStore(tmp_path / "safety.json")
    recorder = PersistentOperationalRecorder(store=store, safety_store=safety)
    snapshot = _snapshot(9)

    def fail_append(_record):
        raise OSError("memory persistence failure")

    monkeypatch.setattr(store, "append", fail_append)

    with pytest.raises(OSError, match="memory persistence failure"):
        recorder.record_operation(snapshot, timestamp=datetime.now(timezone.utc))

    restored_safety = OperationalSafetyStore(tmp_path / "safety.json")
    audit, _ = restored_safety.load()
    assert len(audit.records()) == 1
    assert store.load().records() == ()


def test_record_operation_does_not_duplicate_after_post_commit_reload_failure(tmp_path, monkeypatch):
    store = OperationMemoryStore(tmp_path / "memory.json")
    safety = OperationalSafetyStore(tmp_path / "safety.json")
    recorder = PersistentOperationalRecorder(store=store, safety_store=safety)
    snapshot = _snapshot(10)

    original_reload_memory = recorder._reload_memory
    calls = {"count": 0}

    def flaky_reload():
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("refresh failure")
        return original_reload_memory()

    monkeypatch.setattr(recorder, "_reload_memory", flaky_reload)

    recorded = recorder.record_operation(snapshot, timestamp=datetime.now(timezone.utc))
    assert recorded.memory in store.load().records()
    assert len(store.load().records()) == 1



def test_save_rejects_divergent_snapshot_after_competing_append(tmp_path):
    path = tmp_path / "memory.json"
    first = OperationMemoryStore(path)
    second = OperationMemoryStore(path)
    now = datetime.now(timezone.utc)

    base = OperationMemory()
    base.append(OperationMemoryRecord(now, Signal.COMPRA, 80, "EXECUTAR", "base"))
    first.save(base)

    stale = second.load()
    first.append(OperationMemoryRecord(now, Signal.VENDA, 81, "EXECUTAR", "first append"))
    stale.append(OperationMemoryRecord(now, Signal.COMPRA, 82, "EXECUTAR", "stale append"))

    with pytest.raises(ValueError, match="sobrescrita destrutiva recusada"):
        second.save(stale)

    restored = OperationMemoryStore(path).load().records()
    assert len(restored) == 2
    assert restored[-1].reason == "first append"


def test_record_operation_retry_after_audit_commit_before_memory_failure_is_idempotent(tmp_path, monkeypatch):
    memory_path = tmp_path / "memory.json"
    safety_path = tmp_path / "safety.json"
    recorder = PersistentOperationalRecorder.from_path(memory_path, safety_path=safety_path)
    snapshot = DecisionSnapshot(
        signal="COMPRA",
        analysis_score=90,
        confirmed=True,
        quality_score=90,
        quality_level="A",
        actionable=True,
        decision="EXECUTAR",
        decision_reason="persistência",
        market_context=None,
        market_direction=None,
        market_score=None,
        operational_state_available=True,
        trades_today=0,
        consecutive_losses=0,
        symbol="TEST",
        timeframe="5m",
    )
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    original_append = recorder.store.append
    calls = {"count": 0}

    def fail_once(record):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("simulated memory persistence failure")
        return original_append(record)

    monkeypatch.setattr(recorder.store, "append", fail_once)

    with pytest.raises(OSError, match="simulated memory persistence failure"):
        recorder.record_operation(snapshot, timestamp=timestamp)

    persisted_audit, _ = recorder.safety_store.load()
    assert len(persisted_audit.records()) == 1
    assert recorder.memory.records() == ()

    retry = recorder.record_operation(snapshot, timestamp=timestamp)
    restored = PersistentOperationalRecorder.from_path(memory_path, safety_path=safety_path)

    assert len(restored.memory.records()) == 1
    assert len(restored.audit.records()) == 1
    assert retry.memory == restored.memory.records()[0]


def test_record_operation_retry_after_ambiguous_memory_commit_is_idempotent(tmp_path, monkeypatch):
    store = OperationMemoryStore(tmp_path / "memory.json")
    safety = OperationalSafetyStore(tmp_path / "safety.json")
    recorder = PersistentOperationalRecorder(store=store, safety_store=safety)
    snapshot = _snapshot(11)
    original_append = store.append
    calls = {"count": 0}

    def append_then_fail(record):
        calls["count"] += 1
        original_append(record)
        if calls["count"] == 1:
            raise OSError("failure after durable memory commit")

    monkeypatch.setattr(store, "append", append_then_fail)

    timestamp = datetime.now(timezone.utc)
    with pytest.raises(OSError, match="failure after durable memory commit"):
        recorder.record_operation(snapshot, timestamp=timestamp)

    monkeypatch.setattr(store, "append", original_append)
    recorder._reload_memory()
    recorder._reload_safety()

    retry = recorder.record_operation(snapshot, timestamp=timestamp)

    records = store.load().records()
    audit = safety.load()[0].records()
    assert len(records) == 1
    assert len(audit) == 1
    assert records[0] == retry.memory


def test_operation_memory_rejects_mixed_timezone_awareness(tmp_path):
    path = tmp_path / "memory.json"
    store = OperationMemoryStore(path)
    naive = OperationMemoryRecord(
        datetime(2026, 1, 1),
        Signal.COMPRA,
        80,
        "EXECUTAR",
        "naive",
    )
    aware = OperationMemoryRecord(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        Signal.VENDA,
        81,
        "EXECUTAR",
        "aware",
    )
    store.append(naive)
    with pytest.raises(ValueError, match="mesmo regime de timezone"):
        store.append(aware)


def test_decision_audit_rejects_mixed_timezone_awareness():
    audit = DecisionAudit()
    audit.append(DecisionAuditRecord(datetime(2026, 1, 1), _snapshot(12)))
    with pytest.raises(ValueError, match="mesmo regime de timezone"):
        audit.append(
            DecisionAuditRecord(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                _snapshot(13),
            )
        )


def test_lifecycle_rejects_mixed_timezone_awareness(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    store.put(
        ExecutionLifecycleRecord(
            "req-timezone",
            ExecutionLifecycleState.PENDING,
            datetime(2026, 1, 1),
        )
    )
    with pytest.raises(ValueError, match="mesmo regime de timezone"):
        store.put(
            ExecutionLifecycleRecord(
                "req-timezone",
                ExecutionLifecycleState.PENDING,
                datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )


def test_execution_audit_rejects_mixed_timezone_awareness(tmp_path):
    store = OperationalSafetyStore(tmp_path / "safety.json")
    store.append_execution_audit(
        {
            "request_id": "req-timezone",
            "state": "PENDING",
            "timestamp": "2026-01-01T00:00:00",
            "message": "naive",
        }
    )
    with pytest.raises(ValueError, match="mesmo regime de timezone"):
        store.append_execution_audit(
            {
                "request_id": "req-timezone-2",
                "state": "PENDING",
                "timestamp": "2026-01-01T00:00:01+00:00",
                "message": "aware",
            }
        )


def test_checkpoint_rejects_mixed_timezone_awareness(tmp_path):
    store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    store.save(RuntimeCheckpoint("s-timezone", 1, "req-1", datetime(2026, 1, 1)))
    with pytest.raises(ValueError, match="mesmo regime de timezone"):
        store.save(
            RuntimeCheckpoint(
                "s-timezone",
                2,
                "req-2",
                datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )

def test_recovery_blocks_orphaned_terminal_ledger(tmp_path):
    checkpoint_store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    lifecycle_store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    memory = OperationMemory()

    ledger.reserve("req-orphan")
    ledger.mark_accepted("req-orphan")

    assessment = RecoveryCoordinator(
        checkpoint_store=checkpoint_store,
        lifecycle_store=lifecycle_store,
        execution_ledger=ledger,
        memory=memory,
    ).assess()

    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.can_resume is False
    assert "ledger terminal sem lifecycle" in assessment.message

def test_recovery_blocks_orphaned_terminal_lifecycle(tmp_path):
    checkpoint_store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    lifecycle_store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    memory = OperationMemory()

    lifecycle_store.put(
        ExecutionLifecycleRecord(
            "req-orphan-lifecycle",
            ExecutionLifecycleState.ACCEPTED,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            "accepted without ledger",
        )
    )

    assessment = RecoveryCoordinator(
        checkpoint_store=checkpoint_store,
        lifecycle_store=lifecycle_store,
        execution_ledger=ledger,
        memory=memory,
    ).assess()

    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.can_resume is False
    assert "lifecycle/ledger inconsistente" in assessment.message
