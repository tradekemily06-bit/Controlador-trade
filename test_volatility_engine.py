from datetime import datetime, timedelta

import pytest

from core.market_data import Candle
from core.volatility_engine import VolatilityEngine


def make_candle(
    index,
    *,
    open_price,
    high,
    low,
    close,
):
    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=index),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def test_detects_high_volatility():
    candles = [
        make_candle(0, open_price=100, high=102, low=98, close=100),
        make_candle(1, open_price=100, high=102, low=98, close=100),
    ]

    result = VolatilityEngine().evaluate(candles=candles)

    assert result.score == 100.0
    assert result.average_range_percent == pytest.approx(4.0)


def test_detects_adequate_volatility():
    candles = [
        make_candle(0, open_price=100, high=100.4, low=99.6, close=100),
        make_candle(1, open_price=100, high=100.4, low=99.6, close=100),
    ]

    result = VolatilityEngine().evaluate(candles=candles)

    assert result.score == 70.0
    assert result.average_range_percent == pytest.approx(0.8)


def test_detects_moderate_volatility():
    candles = [
        make_candle(0, open_price=100, high=100.2, low=99.8, close=100),
        make_candle(1, open_price=100, high=100.2, low=99.8, close=100),
    ]

    result = VolatilityEngine().evaluate(candles=candles)

    assert result.score == 40.0
    assert result.average_range_percent == pytest.approx(0.4)


def test_detects_very_low_volatility():
    candles = [
        make_candle(0, open_price=100, high=100.05, low=99.95, close=100),
        make_candle(1, open_price=100, high=100.05, low=99.95, close=100),
    ]

    result = VolatilityEngine().evaluate(candles=candles)

    assert result.score == 10.0
    assert result.average_range_percent == pytest.approx(0.1)


def test_uses_average_range():
    candles = [
        make_candle(0, open_price=100, high=102, low=98, close=100),
        make_candle(1, open_price=100, high=100.2, low=99.8, close=100),
    ]

    result = VolatilityEngine().evaluate(candles=candles)

    assert result.average_range_percent == pytest.approx(2.2)


def test_requires_at_least_two_candles():
    candles = [
        make_candle(0, open_price=100, high=102, low=98, close=100),
    ]

    with pytest.raises(ValueError):
        VolatilityEngine().evaluate(candles=candles)
