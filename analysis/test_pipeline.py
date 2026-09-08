from datetime import datetime, timedelta

import pytest

from analysis.pipeline import StrategyPipeline
from core.models import Signal
from data.models import Candle


BASE = datetime(2026, 1, 1, 10, 0, 0)


def candle(offset, open_, high, low, close, volume=1000):
    return Candle(
        timestamp=BASE + timedelta(minutes=offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def rising_candles():
    return [
        candle(0, 100, 105, 95, 102, 1000),
        candle(1, 102, 108, 100, 106, 1000),
        candle(2, 106, 112, 104, 110, 1500),
    ]


def test_pipeline_connects_candles_to_buy_signal():
    result = StrategyPipeline().evaluate(
        rising_candles(),
        confirmed=True,
        symbol="TEST",
        timeframe="5m",
    )

    assert result.signal == Signal.COMPRA
    assert result.confirmed is True
    assert result.symbol == "TEST"
    assert result.timeframe == "5m"
    assert 70 <= result.score <= 100


def test_pipeline_waits_without_confirmation():
    result = StrategyPipeline().evaluate(
        rising_candles(),
        confirmed=False,
    )

    assert result.signal == Signal.AGUARDAR
    assert result.confirmed is False


def test_pipeline_respects_filters():
    result = StrategyPipeline().evaluate(
        rising_candles(),
        confirmed=True,
        filters_ok=False,
    )

    assert result.signal == Signal.AGUARDAR
    assert "Filtros" in result.reason


def test_pipeline_requires_candles():
    with pytest.raises(ValueError, match="pelo menos um candle"):
        StrategyPipeline().evaluate([])
