from datetime import datetime, timedelta

import pytest

from core.market_context import MarketDirection
from core.market_data import Candle
from core.trend_engine import TrendEngine


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


def test_detects_strong_uptrend():
    candles = [
        make_candle(0, open_price=100, high=105, low=95, close=103),
        make_candle(1, open_price=103, high=110, low=100, close=108),
        make_candle(2, open_price=108, high=115, low=105, close=113),
    ]

    result = TrendEngine().evaluate(candles=candles)

    assert result.direction == MarketDirection.ALTA
    assert result.strength == 100.0


def test_detects_strong_downtrend():
    candles = [
        make_candle(0, open_price=113, high=115, low=105, close=108),
        make_candle(1, open_price=108, high=110, low=100, close=103),
        make_candle(2, open_price=103, high=105, low=95, close=98),
    ]

    result = TrendEngine().evaluate(candles=candles)

    assert result.direction == MarketDirection.BAIXA
    assert result.strength == 100.0


def test_detects_weak_upward_movement():
    candles = [
        make_candle(0, open_price=100, high=105, low=95, close=100),
        make_candle(1, open_price=100, high=103, low=97, close=101),
        make_candle(2, open_price=101, high=104, low=98, close=102),
    ]

    result = TrendEngine().evaluate(candles=candles)

    assert result.direction == MarketDirection.ALTA
    assert result.strength == 50.0


def test_detects_weak_downward_movement():
    candles = [
        make_candle(0, open_price=102, high=105, low=98, close=102),
        make_candle(1, open_price=102, high=104, low=99, close=101),
        make_candle(2, open_price=101, high=103, low=97, close=100),
    ]

    result = TrendEngine().evaluate(candles=candles)

    assert result.direction == MarketDirection.BAIXA
    assert result.strength == 50.0


def test_detects_neutral_market():
    candles = [
        make_candle(0, open_price=100, high=105, low=95, close=100),
        make_candle(1, open_price=100, high=104, low=96, close=100),
        make_candle(2, open_price=100, high=105, low=95, close=100),
    ]

    result = TrendEngine().evaluate(candles=candles)

    assert result.direction == MarketDirection.NEUTRA
    assert result.strength == 0.0


def test_requires_at_least_three_candles():
    candles = [
        make_candle(0, open_price=100, high=105, low=95, close=103),
        make_candle(1, open_price=103, high=110, low=100, close=108),
    ]

    with pytest.raises(ValueError):
        TrendEngine().evaluate(candles=candles)
