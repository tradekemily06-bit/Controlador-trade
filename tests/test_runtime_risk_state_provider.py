from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.operational_state import OperationalState
from core.operational_runtime import build_operational_runtime
from core.runtime_risk_state_provider import RuntimeRiskStateProvider


def _state(*, trades_today: int = 0) -> OperationalState:
    return OperationalState(
        balance=1000.0,
        equity=1000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        trades_today=trades_today,
        consecutive_losses=0,
        open_positions=0,
        net_position=0.0,
        exposure=0.0,
        market_open=True,
        last_processed_candle=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )


def test_runtime_risk_provider_reads_fresh_getter_without_fallback():
    state = _state(trades_today=1)
    provider = RuntimeRiskStateProvider(lambda: state)

    assert provider.current_risk_state() is state


def test_runtime_risk_provider_rejects_invalid_getter_result():
    provider = RuntimeRiskStateProvider(lambda: object())

    with pytest.raises(TypeError, match="invalid state"):
        provider.current_risk_state()


def test_operational_runtime_passes_explicit_risk_provider_to_gateway(tmp_path):
    provider = RuntimeRiskStateProvider(lambda: _state())

    runtime = build_operational_runtime(tmp_path, risk_state_provider=provider)

    assert runtime.gateway._risk_state_provider is provider


def test_operational_runtime_keeps_provider_absent_by_default(tmp_path):
    runtime = build_operational_runtime(tmp_path)

    assert runtime.gateway._risk_state_provider is not None
