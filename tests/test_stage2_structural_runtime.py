from __future__ import annotations

from pathlib import Path

import pytest

from core.operational_barrier_factory import build_global_operational_barrier
from core.operational_runtime import build_operational_runtime


def test_runtime_incident_barrier_is_durable_across_restart(tmp_path: Path):
    runtime = build_operational_runtime(tmp_path)
    incident = runtime.incident_manager.open_incident(title="Falha de teste", message="executor indisponível", incident_id="incident-test")
    assert incident.incident_id == "incident-test"
    assert runtime.incident_manager.execution_blocked() is True

    restarted = build_operational_runtime(tmp_path)
    assert restarted.incident_manager.execution_blocked() is True
    decision = build_global_operational_barrier(restarted).evaluate()
    assert decision.operationally_allowed is False
    assert "technical-incident" in decision.blocking_components


def test_public_multi_instance_local_runtime_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    monkeypatch.setenv("CONTROLADOR_MULTI_INSTANCE", "true")
    with pytest.raises(RuntimeError, match="shared authoritative operational state provider"):
        build_operational_runtime(tmp_path)
