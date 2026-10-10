"""Deterministic indicator evidence derived from validated market candles.

This layer explains market evidence only. It never creates or authorizes an order.
External indicator providers can later normalize their readings into the same contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Sequence

from data.models import Candle


class IndicatorBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    MIXED = "MIXED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class IndicatorEvidence:
    """Auditable indicator values for one symbol/timeframe candle series."""

    source: str
    candle_timestamp: datetime
    candles_used: int
    ema_fast: float
    ema_slow: float
    rsi_14: float
    macd: float
    macd_signal: float
    atr_14: float
    bias: IndicatorBias
    bullish_votes: int
    bearish_votes: int
    reason: str

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source must be non-empty")
        if self.candles_used < 35:
            raise ValueError("at least 35 candles are required")
        for name in ("ema_fast", "ema_slow", "rsi_14", "macd", "macd_signal", "atr_14"):
            value = getattr(self, name)
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.rsi_14 <= 100:
            raise ValueError("rsi_14 must be between 0 and 100")
        if self.atr_14 < 0:
            raise ValueError("atr_14 cannot be negative")
        if self.bullish_votes < 0 or self.bearish_votes < 0:
            raise ValueError("vote counts cannot be negative")


def _ema(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        raise ValueError("insufficient values for EMA")
    alpha = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    result = [current]
    for value in values[period:]:
        current = alpha * value + (1 - alpha) * current
        result.append(current)
    return result


def _rsi(values: Sequence[float], period: int = 14) -> float:
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    if len(changes) < period:
        raise ValueError("insufficient values for RSI")
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    relative_strength = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def calculate_indicator_evidence(
    candles: Sequence[Candle],
    *,
    source: str = "CONTROLADOR_CALCULADO",
) -> IndicatorEvidence:
    """Calculate EMA(9/21), RSI(14), MACD(12/26/9), and ATR(14).

    Input must be a chronological sequence of validated candles. The caller is
    responsible for requesting closed candles from its market-data provider.
    """
    items = tuple(candles)
    if len(items) < 35:
        raise ValueError("at least 35 candles are required for indicator evidence")
    if not source or not source.strip():
        raise ValueError("source must be non-empty")
    if any(not candle.is_valid() for candle in items):
        raise ValueError("indicator input contains invalid candles")
    if any(items[i].timestamp >= items[i + 1].timestamp for i in range(len(items) - 1)):
        raise ValueError("candles must be strictly chronological")

    closes = [float(c.close) for c in items]
    ema_fast_series = _ema(closes, 9)
    ema_slow_series = _ema(closes, 21)
    ema_fast, ema_slow = ema_fast_series[-1], ema_slow_series[-1]

    ema_12 = _ema(closes, 12)
    ema_26 = _ema(closes, 26)
    # Align both EMA streams to the same final 26-period starting index.
    macd_series = [
        fast - slow
        for fast, slow in zip(ema_12[-len(ema_26):], ema_26)
    ]
    macd_signal = _ema(macd_series, 9)[-1]
    macd = macd_series[-1]
    rsi = _rsi(closes, 14)

    true_ranges = []
    for index, candle in enumerate(items):
        if index == 0:
            true_ranges.append(float(candle.high - candle.low))
        else:
            previous_close = closes[index - 1]
            true_ranges.append(max(
                float(candle.high - candle.low),
                abs(float(candle.high) - previous_close),
                abs(float(candle.low) - previous_close),
            ))
    atr_values = true_ranges[:14]
    atr = sum(atr_values) / 14
    for true_range in true_ranges[14:]:
        atr = (atr * 13 + true_range) / 14

    bullish_votes = int(ema_fast > ema_slow) + int(macd > macd_signal) + int(rsi >= 55)
    bearish_votes = int(ema_fast < ema_slow) + int(macd < macd_signal) + int(rsi <= 45)
    if bullish_votes >= 2 and bullish_votes > bearish_votes:
        bias = IndicatorBias.BULLISH
    elif bearish_votes >= 2 and bearish_votes > bullish_votes:
        bias = IndicatorBias.BEARISH
    else:
        bias = IndicatorBias.MIXED

    return IndicatorEvidence(
        source=source.strip(),
        candle_timestamp=items[-1].timestamp,
        candles_used=len(items),
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi_14=rsi,
        macd=macd,
        macd_signal=macd_signal,
        atr_14=atr,
        bias=bias,
        bullish_votes=bullish_votes,
        bearish_votes=bearish_votes,
        reason=(
            f"EMA9/21={'alta' if ema_fast > ema_slow else 'baixa' if ema_fast < ema_slow else 'neutra'}; "
            f"RSI14={rsi:.2f}; MACD={'positivo' if macd > macd_signal else 'negativo' if macd < macd_signal else 'neutro'}; "
            "indicadores são evidências, não autorização de operação."
        ),
    )
