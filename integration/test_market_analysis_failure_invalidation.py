from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.models import Candle
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


def _healthy_state():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(base + timedelta(minutes=i), 100, 101, 99, 100, 1)
        for i in range(3)
    )
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    state.update(
        BrokerMarketDataSnapshot(
            symbol="EURUSD",
            timeframe="1m",
            candles=candles,
            source="TEST_PROVIDER",
            received_at=base,
        ),
        now=base + timedelta(minutes=3),
        expected_interval_seconds=60,
    )
    assert state.status()["health"] == "HEALTHY"
    return state


def test_failed_mt5_operational_read_invalidates_previous_market_state():
    state = _healthy_state()
    service = object.__new__(ConfiguredEcosystemService)
    service.trading_runtime = SimpleNamespace(market_data_state=state)
    service.operational_runtime = object()
    service.execution_provider = "ic_markets_mt5_demo"
    service.preferences = SimpleNamespace(
        preferences=SimpleNamespace(require_closed_candle=True, require_filters=True)
    )

    def fail_read():
        raise RuntimeError("terminal MT5 indisponível")

    service.mt5_operational_adapter = SimpleNamespace(read_operational_state=fail_read)

    with pytest.raises(RuntimeError, match="terminal MT5 indisponível"):
        service.analyze_mt5_market(symbol="EURUSD", timeframe="1m", limit=20)

    status = state.status()
    assert status["health"] == "NOT_CONNECTED"
    assert status["safe_for_analysis"] is False
    assert status["source"] is None
    assert status["message"] == "ciclo de análise indisponível: RuntimeError"
