from datetime import datetime, timezone
import json
import threading

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.operational_safety_store import OperationalSafetyStore
from core.persistent_operational_recorder import PersistentOperationalRecorder
from core.decision_audit import DecisionAudit
from core.kill_switch import KillSwitch


def snapshot() -> DecisionSnapshot:
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=82.0, confirmed=True,
        quality_score=88.0, quality_level="FORTE", actionable=True,
        decision="EXECUTAR", decision_reason="contexto e risco favoráveis",
        market_context="ALTA", market_direction="COMPRA", market_score=80.0,
        operational_state_available=True, trades_today=1, consecutive_losses=0,
        symbol="TEST", timeframe="5m",
    )


def test_audit_and_kill_switch_survive_restart(tmp_path):
    path = tmp_path / "operations.json"
    safety_path = tmp_path / "safety.json"
    recorder = PersistentOperationalRecorder.from_path(path, safety_path=safety_path)
    timestamp = datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc)

    record = recorder.record_decision(snapshot(), timestamp=timestamp)
    recorder.activate_kill_switch("limite operacional atingido")

    restored = PersistentOperationalRecorder.from_path(path, safety_path=safety_path)
    assert restored.audit.records() == (record,)
    assert restored.kill_switch.state.enabled is True
    assert restored.kill_switch.state.reason == "limite operacional atingido"
    assert restored.can_execute() is False


def test_explicit_kill_switch_cannot_override_persisted_block(tmp_path):
    path = tmp_path / "operations.json"
    safety_path = tmp_path / "safety.json"
    first = PersistentOperationalRecorder.from_path(path, safety_path=safety_path)
    first.activate_kill_switch("persistir bloqueio")

    supplied = first.kill_switch.__class__()
    restored = PersistentOperationalRecorder.from_path(path, safety_path=safety_path, kill_switch=supplied)
    assert restored.can_execute() is False
    assert restored.kill_switch.state.reason == "persistir bloqueio"


def test_kill_switch_deactivation_is_persistent(tmp_path):
    path = tmp_path / "operations.json"
    safety_path = tmp_path / "safety.json"
    recorder = PersistentOperationalRecorder.from_path(path, safety_path=safety_path)
    recorder.activate_kill_switch("teste")
    recorder.deactivate_kill_switch()

    restored = PersistentOperationalRecorder.from_path(path, safety_path=safety_path)
    assert restored.kill_switch.state.enabled is False
    assert restored.kill_switch.state.reason is None
    assert restored.can_execute() is True


def test_invalid_safety_state_fails_closed(tmp_path):
    path = tmp_path / "operations.json"
    safety_path = tmp_path / "safety.json"
    safety_path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="estado de segurança inválido"):
        PersistentOperationalRecorder.from_path(path, safety_path=safety_path)


def test_safety_store_requires_valid_dependencies(tmp_path):
    store = OperationalSafetyStore(tmp_path / "safety.json")
    with pytest.raises(TypeError, match="audit deve ser DecisionAudit"):
        store.save(object(), object())


def test_safety_store_atomic_failure_preserves_existing_durable_state(tmp_path, monkeypatch):
    path = tmp_path / "safety.json"
    store = OperationalSafetyStore(path)
    kill_switch = KillSwitch()
    kill_switch.activate("durable block")
    store.save(DecisionAudit(), kill_switch)
    original = path.read_text(encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("commit failed")

    monkeypatch.setattr("core.durable_json.os.replace", fail_replace)

    with pytest.raises(OSError, match="não foi possível persistir o estado de segurança"):
        store.save(DecisionAudit(), KillSwitch())

    assert path.read_text(encoding="utf-8") == original
    restored_audit, restored_kill = store.load()
    assert restored_audit.records() == ()
    assert restored_kill.state.enabled is True
    assert restored_kill.state.reason == "durable block"
    assert json.loads(original)["kill_switch"]["enabled"] is True


def test_safety_reload_never_clears_live_kill_switch(tmp_path):
    path = tmp_path / "operations.json"
    safety_path = tmp_path / "safety.json"
    recorder = PersistentOperationalRecorder.from_path(path, safety_path=safety_path)

    # A direct live activation represents an emergency stop that has not yet
    # reached durable storage. A recovery refresh must not accidentally clear it.
    recorder.kill_switch.activate("emergency local stop")
    recorder._reload_safety()

    assert recorder.kill_switch.state.enabled is True
    assert recorder.kill_switch.state.reason == "emergency local stop"


def test_persistent_kill_switch_window_serializes_safety_updates(tmp_path):
    store = OperationalSafetyStore(tmp_path / "safety.json")
    clear = KillSwitch()
    store.save(DecisionAudit(), clear)
    entered = threading.Event()
    release = threading.Event()
    writer_done = threading.Event()

    def writer():
        blocked = KillSwitch()
        blocked.activate("emergency from another worker")
        with store.kill_switch_execution_window() as state:
            assert state.enabled is False
            entered.set()
            release.wait(timeout=2)

    thread = threading.Thread(target=writer)
    thread.start()
    assert entered.wait(timeout=2)

    def persist_activation():
        blocked = KillSwitch()
        blocked.activate("emergency from another worker")
        store.save_kill_switch(blocked)
        writer_done.set()

    updater = threading.Thread(target=persist_activation)
    updater.start()
    assert not writer_done.wait(timeout=0.2)
    release.set()
    updater.join(timeout=2)
    thread.join(timeout=2)
    assert writer_done.is_set()
    _, restored = store.load()
    assert restored.state.enabled is True
    assert restored.state.reason == "emergency from another worker"
