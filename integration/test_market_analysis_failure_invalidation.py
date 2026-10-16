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


def test_invalid_market_payload_is_reported_as_unavailable_and_invalidates_state():
    state = _healthy_state()
    service = object.__new__(ConfiguredEcosystemService)
    service.trading_runtime = SimpleNamespace(
        market_data_state=state,
        orchestrator=SimpleNamespace(
            evaluate=lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("provider returned no candles"))
        ),
    )
    service.operational_runtime = object()
    service.execution_provider = "ic_markets_mt5_demo"
    service.preferences = SimpleNamespace(
        preferences=SimpleNamespace(require_closed_candle=True, require_filters=True)
    )
    service.mt5_operational_adapter = SimpleNamespace(read_operational_state=lambda: None)

    with pytest.raises(RuntimeError, match="dados/contexto de mercado indisponíveis: ValueError"):
        service.analyze_mt5_market(symbol="EURUSD", timeframe="1m", limit=20)

    status = state.status()
    assert status["health"] == "NOT_CONNECTED"
    assert status["safe_for_analysis"] is False
    assert status["source"] is None


def test_stale_market_snapshot_never_returns_or_records_directional_analysis():
    state = _healthy_state()
    now = datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale_candles = tuple(
        Candle(base + timedelta(minutes=i), 100, 101, 99, 100, 1)
        for i in range(3)
    )
    orchestration = SimpleNamespace(
        timestamp=now,
        market_data=SimpleNamespace(
            source="TEST_PROVIDER",
            candles=stale_candles,
        ),
        analysis=SimpleNamespace(signal=SimpleNamespace(value="COMPRA")),
    )
    service = object.__new__(ConfiguredEcosystemService)
    service.trading_runtime = SimpleNamespace(
        market_data_state=state,
        orchestrator=SimpleNamespace(evaluate=lambda *args, **kwargs: orchestration),
    )
    service.operational_runtime = object()
    service.execution_provider = "ic_markets_mt5_demo"
    service.preferences = SimpleNamespace(
        preferences=SimpleNamespace(require_closed_candle=True, require_filters=True)
    )
    service.mt5_operational_adapter = SimpleNamespace(read_operational_state=lambda: None)
    service._record_analysis = lambda _: pytest.fail("análise insegura não pode ser registrada")

    with pytest.raises(RuntimeError, match="dados de mercado não seguros para análise: STALE"):
        service.analyze_mt5_market(symbol="EURUSD", timeframe="1m", limit=20)

    status = state.status()
    assert status["health"] == "STALE"
    assert status["safe_for_analysis"] is False
    assert status["source"] == "TEST_PROVIDER"
