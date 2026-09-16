from pathlib import Path

import pytest

from core.operational_runtime import build_operational_runtime


def test_public_multi_instance_startup_fails_closed(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    monkeypatch.setenv("CONTROLADOR_MULTI_INSTANCE", "true")
    with pytest.raises(RuntimeError, match="shared authoritative operational state provider"):
        build_operational_runtime(tmp_path)


def test_single_instance_runtime_owns_persistent_operational_state(tmp_path: Path):
    runtime = build_operational_runtime(tmp_path)
    assert runtime.execution_ledger.path == tmp_path / "execution-ledger.json"
    assert runtime.execution_lifecycle.path == tmp_path / "execution-lifecycle.json"
    assert runtime.checkpoint_store.path == tmp_path / "runtime-checkpoint.json"
    assert runtime.safety_store.path == tmp_path / "operational-safety.json"
    assert runtime.incident_store.path == tmp_path / "technical-incident.json"
    assert runtime.demo_risk_state is not None


def test_corrupt_persistent_safety_state_fails_closed(tmp_path: Path):
    safety_path = tmp_path / "operational-safety.json"
    safety_path.write_text("{not-json", encoding="utf-8")
    runtime = build_operational_runtime(tmp_path)
    assert runtime.kill_switch.state.enabled is True
    assert "indisponível" in runtime.kill_switch.state.reason
