from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.operational_runtime import build_operational_runtime
from core.operational_state import OperationalState
from core.runtime_risk_state_provider import RuntimeRiskStateProvider
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from integration.execution_provider import build_demo_execution_port


def _risk_state() -> OperationalState:
    return OperationalState(
        balance=1000.0,
        equity=1000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        trades_today=0,
        consecutive_losses=0,
        open_positions=0,
        net_position=0.0,
        exposure=0.0,
        market_open=True,
        last_processed_candle=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )


def test_selected_mt5_demo_provider_requires_authoritative_risk_state(tmp_path: Path):
    executor = build_demo_execution_port("ic_markets_mt5_demo", symbol="EURUSD")
    with pytest.raises(RuntimeError, match="authoritative risk-state provider"):
        build_operational_runtime(tmp_path, executor=executor)


def test_selected_mt5_demo_provider_can_be_injected_with_risk_state(tmp_path: Path):
    executor = build_demo_execution_port("ic_markets_mt5_demo", symbol="EURUSD")
    provider = RuntimeRiskStateProvider(_risk_state)
    runtime = build_operational_runtime(
        tmp_path,
        executor=executor,
        risk_state_provider=provider,
    )
    assert isinstance(runtime.gateway._executor, ICMarketsMT5DemoAdapter)
    assert runtime.gateway._risk_state_provider is provider
