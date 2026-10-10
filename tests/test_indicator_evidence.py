from datetime import datetime, timedelta

import pytest

from core.indicator_evidence import IndicatorBias, calculate_indicator_evidence
from data.models import Candle


def candles_from_closes(closes):
    result = []
    for index, close in enumerate(closes):
        previous = closes[index - 1] if index else close
        result.append(Candle(
            timestamp=datetime(2026, 1, 1) + timedelta(minutes=index),
            open=float(previous),
            high=float(max(previous, close) + 0.5),
            low=float(min(previous, close) - 0.5),
            close=float(close),
            volume=100.0,
        ))
    return result


def test_uptrend_produces_bullish_indicator_evidence_without_order_authority():
    closes = [100 + index * 0.5 for index in range(40)]
    result = calculate_indicator_evidence(candles_from_closes(closes))

    assert result.bias is IndicatorBias.BULLISH
    assert result.ema_fast > result.ema_slow
    assert result.rsi_14 > 55
    assert result.atr_14 > 0
    assert result.source == "CONTROLADOR_CALCULADO"
    assert "não autorização" in result.reason


def test_downtrend_produces_bearish_indicator_evidence():
    closes = [120 - index * 0.5 for index in range(40)]
    result = calculate_indicator_evidence(candles_from_closes(closes))

    assert result.bias is IndicatorBias.BEARISH
    assert result.ema_fast < result.ema_slow
    assert result.rsi_14 < 45


def test_requires_enough_candles_for_macd_signal():
    with pytest.raises(ValueError, match="35 candles"):
        calculate_indicator_evidence(candles_from_closes([100 + i for i in range(34)]))


def test_rejects_non_chronological_candles():
    candles = candles_from_closes([100 + i * 0.1 for i in range(40)])
    candles[10], candles[11] = candles[11], candles[10]

    with pytest.raises(ValueError, match="chronological"):
        calculate_indicator_evidence(candles)


def test_rejects_empty_source():
    with pytest.raises(ValueError, match="source"):
        calculate_indicator_evidence(
            candles_from_closes([100 + i * 0.1 for i in range(40)]),
            source=" ",
        )
