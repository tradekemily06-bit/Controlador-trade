from datetime import datetime, timezone
from threading import Thread

import pytest

from core.decision_audit import DecisionAudit
from core.durable_json import atomic_write_json
from core.kill_switch import KillSwitch
from core.operation_memory import OperationMemory
from core.operation_memory_store import OperationMemoryStore
from core.operational_safety_store import OperationalSafetyStore
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
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

    monkeypatch.setattr(recorder.safety_store, "save", fail_save)

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

    monkeypatch.setattr(recorder.safety_store, "save", fail_save)

    with pytest.raises(OSError, match="simulated persistence failure"):
        recorder.deactivate_kill_switch()

    assert recorder.kill_switch.state.enabled is True
    assert recorder.kill_switch.state.reason == "safety stop"
