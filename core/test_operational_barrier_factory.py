from __future__ import annotations

from pathlib import Path

from core.global_operational_barrier import BarrierStatus
from core.operational_barrier_factory import build_global_operational_barrier
from core.operational_runtime import build_operational_runtime
from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest


def test_runtime_build_wires_fresh_global_barrier(tmp_path: Path) -> None:
    runtime = build_operational_runtime(tmp_path)

    # A newly constructed runtime has no market snapshot yet. That must be
    # fail-closed rather than pretending the ecosystem is operational.
    first = build_global_operational_barrier(runtime).evaluate()
    assert first.status is BarrierStatus.BLOCKED
    assert not first.operationally_allowed
    assert "market-data-integrity" in first.blocking_components

    runtime.kill_switch.activate("teste de bloqueio")
    second = build_global_operational_barrier(runtime).evaluate()

    assert second.status is BarrierStatus.BLOCKED
    assert not second.operationally_allowed
    assert "kill-switch" in second.blocking_components
    assert "market-data-integrity" in second.blocking_components


def test_gateway_stops_after_runtime_kill_switch_changes(tmp_path: Path) -> None:
    runtime = build_operational_runtime(tmp_path)
    request = ExecutionRequest("TEST", Signal.COMPRA, 1.0, 60, ExecutionMode.DEMO)

    runtime.kill_switch.activate("bloqueio de segurança")
    result = runtime.gateway.execute("blocked-after-runtime-change", request)

    assert result.accepted is False
    assert "kill" in result.message.lower()


def test_global_barrier_never_reports_ready_when_safety_store_cannot_be_read(tmp_path: Path, monkeypatch) -> None:
    runtime = build_operational_runtime(tmp_path)

    def fail_load():
        raise OSError("safety store unavailable")

    monkeypatch.setattr(runtime.safety_store, "load", fail_load)
    decision = build_global_operational_barrier(runtime).evaluate()

    assert decision.status is BarrierStatus.BLOCKED
    assert not decision.operationally_allowed
    assert "operational-safety-store" in decision.blocking_components
