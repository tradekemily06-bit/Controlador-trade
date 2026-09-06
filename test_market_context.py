from datetime import datetime, timedelta

import pytest

from core.market_context import (
    MarketContext,
    MarketContextEngine,
    MarketDirection,
)
from core.market_data import Candle


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


def test_integrates_trend_and_volatility_into_context():
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


def test_low_volatility_can_keep_context_neutral():
    candles = [
        make_candle(0, open_price=100, high=100.05, low=99.95, close=100),
        make_candle(1, open_price=100, high=100.05, low=99.95, close=100),
        make_candle(2, open_price=100, high=100.05, low=99.95, close=100),
    ]

    result = MarketContextEngine().evaluate_from_candles(
        candles=candles,
        liquidity_quality=50,
    )

    assert result.context == MarketContext.NEUTRO
    assert result.direction == MarketDirection.NEUTRA


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


def test_requires_candles():
    with pytest.raises(ValueError):
        MarketContextEngine().evaluate_from_candles(
            candles=[],
            liquidity_quality=50,
        )


def test_context_from_candles_integrates_trend_and_volatility():
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


def test_low_volatility_can_keep_context_neutral():
    candles = [
        make_candle(0, open_price=100, high=100.05, low=99.95, close=100),
        make_candle(1, open_price=100, high=100.05, low=99.95, close=100.01),
        make_candle(2, open_price=100.01, high=100.06, low=99.96, close=100.02),
    ]

    result = MarketContextEngine().evaluate_from_candles(
        candles=candles,
        liquidity_quality=50,
    )

    assert result.context == MarketContext.NEUTRO
    assert result.direction == MarketDirection.ALTA


def test_evaluate_from_candles_requires_candles():
    with pytest.raises(ValueError):
        MarketContextEngine().evaluate_from_candles(
            candles=[],
            liquidity_quality=50,
        )


def test_evaluate_from_candles_rejects_invalid_liquidity():
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
