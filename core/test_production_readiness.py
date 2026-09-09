from pathlib import Path

import pytest

from core.kill_switch import KillSwitch
from core.production_readiness import ProductionReadiness, ReadinessState
from execution.execution_ledger import ExecutionLedger
from execution.ports import ExecutionMode


def test_demo_readiness_requires_safe_state(tmp_path: Path) -> None:
    report = ProductionReadiness(
        kill_switch=KillSwitch(),
        execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
    ).evaluate()

    assert report.state is ReadinessState.READY_DEMO
    assert report.ready is True


def test_active_kill_switch_is_not_ready(tmp_path: Path) -> None:
    switch = KillSwitch()
    switch.activate("teste")

    report = ProductionReadiness(
        kill_switch=switch,
        execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
    ).evaluate()

    assert report.state is ReadinessState.NOT_READY
    assert report.ready is False
    assert "kill switch ativo" in report.reasons


def test_dependencies_are_required(tmp_path: Path) -> None:
    ledger = ExecutionLedger(tmp_path / "ledger.json")

    with pytest.raises(ValueError):
        ProductionReadiness(kill_switch=None, execution_ledger=ledger)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        ProductionReadiness(kill_switch=KillSwitch(), execution_ledger=None)  # type: ignore[arg-type]


def test_real_can_never_be_reported_as_ready(tmp_path: Path) -> None:
    report = ProductionReadiness(
        kill_switch=KillSwitch(),
        execution_ledger=ExecutionLedger(tmp_path / "ledger.json"),
    ).evaluate(mode=ExecutionMode.REAL)

    assert report.state is ReadinessState.NOT_READY
    assert report.ready is False
    assert "REAL" in report.reasons[0]
