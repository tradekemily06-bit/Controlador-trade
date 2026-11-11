from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from data.models import Candle
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


def _service_with_history(candles):
    service = object.__new__(ConfiguredEcosystemService)
    service.execution_provider = "ic_markets_mt5_demo"
    service.mt5_market_adapter = SimpleNamespace(
        fetch_market_data=lambda _request: tuple(candles)
    )
    return service


def _valid_candles():
    start = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    return [
        Candle(start, 100.0, 102.0, 99.0, 101.0, 10.0),
        Candle(start + timedelta(minutes=5), 101.0, 103.0, 100.0, 102.0, 12.0),
    ]


@pytest.mark.parametrize("method_name", ["replay_mt5_history", "simulate_mt5_signal_scenario"])
def test_historical_tools_reject_duplicate_candle_timestamps(method_name):
    candles = _valid_candles()
    candles[1] = Candle(
        candles[0].timestamp, 101.0, 103.0, 100.0, 102.0, 12.0
    )
    service = _service_with_history(candles)
    method = getattr(service, method_name)

    with pytest.raises(RuntimeError, match="timestamps duplicados"):
        if method_name == "replay_mt5_history":
            method(symbol="EURUSD", timeframe="5m", limit=100)
        else:
            method(symbol="EURUSD", timeframe="5m", limit=100)


@pytest.mark.parametrize("method_name", ["replay_mt5_history", "simulate_mt5_signal_scenario"])
def test_historical_tools_reject_invalid_ohlc_candles(method_name):
    candles = _valid_candles()
    candles[1] = Candle(
        candles[1].timestamp, 101.0, 99.0, 98.0, 102.0, 12.0
    )
    service = _service_with_history(candles)
    method = getattr(service, method_name)

    with pytest.raises(RuntimeError, match="candle"):
        if method_name == "replay_mt5_history":
            method(symbol="EURUSD", timeframe="5m", limit=100)
        else:
            method(symbol="EURUSD", timeframe="5m", limit=100)

@pytest.mark.parametrize("method_name", ["replay_mt5_history", "simulate_mt5_signal_scenario"])
def test_historical_tools_reject_zero_price_ohlc_candles(method_name):
    candles = _valid_candles()
    candles[1] = Candle(
        candles[1].timestamp, 0.0, 103.0, 0.0, 102.0, 12.0
    )
    service = _service_with_history(candles)
    method = getattr(service, method_name)

    with pytest.raises(RuntimeError, match="candle inválido|OHLC inválido"):
        method(symbol="EURUSD", timeframe="5m", limit=100)
