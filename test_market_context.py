from datetime import datetime, timedelta

import pytest

from core.market_context import (
    MarketContext,
    MarketContextEngine,
    MarketDirection,
)
from core.market_data import Candle


def make_candle(index, *, open_price, high, low, close, volume=100):
    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=index),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_integrates_trend_volatility_and_liquidity():
    candles = [
        make_candle(0, open_price=100, high=101, low=99, close=100),
        make_candle(1, open_price=100, high=102, low=100, close=101),
        make_candle(2, open_price=101, high=103, low=101, close=102),
    ]

    result = MarketContextEngine().evaluate_from_candles(
        candles=candles,
        liquidity_quality=100,
    )

    assert result.context == MarketContext.FAVORAVEL
    assert result.direction == MarketDirection.ALTA
    assert result.score >= 70


def test_low_volatility_with_weak_trend_is_unfavorable():
    candles = [
        make_candle(0, open_price=100, high=100.05, low=99.95, close=100),
        make_candle(1, open_price=100, high=100.05, low=99.95, close=100),
        make_candle(2, open_price=100, high=100.05, low=99.95, close=100),
    ]

    result = MarketContextEngine().evaluate_from_candles(
        candles=candles,
        liquidity_quality=50,
    )

    assert result.context == MarketContext.DESFAVORAVEL
    assert result.direction == MarketDirection.NEUTRA


def test_requires_candles():
    with pytest.raises(ValueError):
        MarketContextEngine().evaluate_from_candles(
            candles=[],
            liquidity_quality=50,
        )


def test_rejects_invalid_liquidity():
    candles = [
        make_candle(0, open_price=100, high=101, low=99, close=100),
        make_candle(1, open_price=100, high=101, low=99, close=100),
        make_candle(2, open_price=100, high=101, low=99, close=100),
    ]

    with pytest.raises(ValueError):
        MarketContextEngine().evaluate_from_candles(
            candles=candles,
            liquidity_quality=101,
        )


def test_rejects_invalid_trend_strength():
    with pytest.raises(ValueError):
        MarketContextEngine().evaluate(
            trend_strength=101,
            volatility_quality=50,
            liquidity_quality=50,
            direction=MarketDirection.ALTA,
        )


def test_rejects_invalid_volatility_quality():
    with pytest.raises(ValueError):
        MarketContextEngine().evaluate(
            trend_strength=50,
            volatility_quality=-1,
            liquidity_quality=50,
            direction=MarketDirection.ALTA,
        )


def test_rejects_invalid_direction():
    with pytest.raises(ValueError):
        MarketContextEngine().evaluate(
            trend_strength=50,
            volatility_quality=50,
            liquidity_quality=50,
            direction="ALTA",
        )


def test_context_is_unfavorable_at_low_score():
    result = MarketContextEngine().evaluate(
        trend_strength=10,
        volatility_quality=10,
        liquidity_quality=10,
        direction=MarketDirection.BAIXA,
    )

    assert result.context == MarketContext.DESFAVORAVEL
    assert result.score == 10


def test_context_is_neutral_between_thresholds():
    result = MarketContextEngine().evaluate(
        trend_strength=50,
        volatility_quality=50,
        liquidity_quality=50,
        direction=MarketDirection.NEUTRA,
    )

    assert result.context == MarketContext.NEUTRO
    assert result.score == 50


def test_context_at_exact_favorable_threshold():
    result = MarketContextEngine().evaluate(
        trend_strength=100,
        volatility_quality=50,
        liquidity_quality=50,
        direction=MarketDirection.ALTA,
    )

    assert result.score == 70
    assert result.context == MarketContext.FAVORAVEL


def test_context_at_exact_unfavorable_threshold():
    result = MarketContextEngine().evaluate(
        trend_strength=0,
        volatility_quality=50,
        liquidity_quality=100 / 3,
        direction=MarketDirection.BAIXA,
    )

    assert result.score == pytest.approx(25, abs=1e-9)
    assert result.context == MarketContext.DESFAVORAVEL
