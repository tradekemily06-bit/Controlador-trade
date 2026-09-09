from datetime import datetime, timezone

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.operational_safety_store import OperationalSafetyStore
from core.persistent_operational_recorder import PersistentOperationalRecorder


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
