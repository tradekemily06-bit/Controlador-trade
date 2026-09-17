from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.kill_switch import KillSwitch
from core.operational_state import OperationalState
from core.risk_state_fingerprint import risk_state_identity
from execution.gateway import ExecutionGateway, GatewayStatus


class Provider:
    def __init__(self, state: OperationalState) -> None:
        self.state = state

    def current_risk_state(self) -> OperationalState:
        return self.state


class Executor:
    def execute(self, request):
        raise AssertionError("executor must not be reached by the barrier tests")


def snapshot_for(state: OperationalState) -> DecisionSnapshot:
    return DecisionSnapshot(
        signal="COMPRA",
        analysis_score=90.0,
        confirmed=True,
        quality_score=90.0,
        quality_level="FORTE",
        actionable=True,
        decision="EXECUTAR",
        decision_reason="teste",
        market_context="NEUTRO",
        market_direction="ALTA",
        market_score=80.0,
        operational_state_available=True,
        trades_today=state.trades_today,
        consecutive_losses=state.consecutive_losses,
        symbol="TEST",
        timeframe="5m",
        risk_state_identity=risk_state_identity(state),
    )


def gateway(provider: Provider) -> ExecutionGateway:
    return ExecutionGateway(Executor(), KillSwitch(), risk_state_provider=provider)


def test_risk_barrier_allows_unchanged_authoritative_state() -> None:
    state = OperationalState(
        balance=1000.0, equity=990.0, realized_pnl=-10.0,
        unrealized_pnl=2.0, trades_today=2, consecutive_losses=1,
        open_positions=1, net_position=1.0, exposure=100.0,
        market_open=True,
    )
    assert gateway(Provider(state))._risk_state_barrier(snapshot_for(state)) is None


@pytest.mark.parametrize("field,changed", [
    ("trades_today", 3),
    ("consecutive_losses", 2),
    ("open_positions", 2),
    ("exposure", 200.0),
    ("balance", 900.0),
    ("equity", 880.0),
    ("realized_pnl", -25.0),
    ("unrealized_pnl", -7.0),
    ("net_position", -1.0),
    ("market_open", False),
    ("last_processed_candle", datetime(2026, 9, 15, 12, 5, tzinfo=timezone.utc)),
])
def test_risk_barrier_blocks_every_risk_state_field_change(field: str, changed) -> None:
    original = OperationalState(
        balance=1000.0, equity=990.0, realized_pnl=-10.0,
        unrealized_pnl=2.0, trades_today=2, consecutive_losses=1,
        open_positions=1, net_position=1.0, exposure=100.0,
        market_open=True,
    )
    current_values = original.__dict__.copy()
    current_values[field] = changed
    current = OperationalState(**current_values)

    result = gateway(Provider(current))._risk_state_barrier(snapshot_for(original))
    assert result is not None
    assert "mudou" in result


def test_risk_barrier_blocks_provider_failure() -> None:
    class BrokenProvider:
        def current_risk_state(self):
            raise RuntimeError("secret backend detail")

    state = OperationalState(trades_today=1, consecutive_losses=0)
    result = gateway(BrokenProvider())._risk_state_barrier(snapshot_for(state))
    assert result is not None
    assert "RuntimeError" in result
    assert "secret backend detail" not in result


def test_risk_barrier_blocks_missing_decision_identity() -> None:
    state = OperationalState(trades_today=1, consecutive_losses=0)
    snapshot = snapshot_for(state)
    snapshot = DecisionSnapshot(**{**snapshot.__dict__, "risk_state_fingerprint": None, "risk_state_identity": None})

    result = gateway(Provider(state))._risk_state_barrier(snapshot)
    assert result is not None
    assert "identidade de risco" in result
