from datetime import datetime, timedelta

import pytest

from core.liquidity_engine import LiquidityEngine
from core.market_data import Candle


def make_candle(index, *, volume):
    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=index),
        open=100,
        high=101,
        low=99,
        close=100,
        volume=volume,
    )


def test_high_relative_volume_gets_high_liquidity_score():
    candles = [
        make_candle(0, volume=100),
        make_candle(1, volume=100),
        make_candle(2, volume=200),
    ]

    result = LiquidityEngine().evaluate(candles=candles)

    assert result.score == 100.0
    assert result.latest_volume == 200
    assert result.volume_ratio >= 1.5
    assert result.reason == "Atividade de volume muito alta."


def test_normal_relative_volume_gets_adequate_score():
    candles = [
        make_candle(0, volume=100),
        make_candle(1, volume=100),
        make_candle(2, volume=100),
    ]

    result = LiquidityEngine().evaluate(candles=candles)

    assert result.score == 75.0
    assert result.volume_ratio == 1.0


def test_low_relative_volume_reduces_score():
    candles = [
        make_candle(0, volume=200),
        make_candle(1, volume=200),
        make_candle(2, volume=50),
    ]

    result = LiquidityEngine().evaluate(candles=candles)

    assert result.score == 10.0
    assert result.volume_ratio < 0.5


def test_requires_at_least_two_candles():
    with pytest.raises(ValueError):
        LiquidityEngine().evaluate(
            candles=[make_candle(0, volume=100)]
        )


def test_zero_average_volume_is_handled():
    candles = [
        make_candle(0, volume=0),
        make_candle(1, volume=0),
    ]

    result = LiquidityEngine().evaluate(candles=candles)

    assert result.score == 0.0
    assert result.volume_ratio == 0.0
    assert "Sem volume suficiente" in result.reason


def test_negative_volume_is_rejected_by_candle():
    with pytest.raises(ValueError):
        make_candle(0, volume=-1)
