from __future__ import annotations

from .models import AnalysisResult, Signal
from .p122_broker_market_data import BrokerMarketDataSnapshot
from .signal_engine import SignalEngine


def evaluate_candle_snapshot(snapshot: BrokerMarketDataSnapshot) -> AnalysisResult:
    """Evaluate completed candles conservatively without broker side effects."""
    candles = snapshot.candles
    if not candles:
        return AnalysisResult(
            Signal.AGUARDAR,
            0,
            "Sem candles suficientes para análise.",
            False,
            snapshot.symbol,
            snapshot.timeframe,
        )

    latest = candles[-1]
    previous = candles[-2] if len(candles) >= 2 else None
    candle_range = latest.high - latest.low
    if candle_range <= 0:
        return AnalysisResult(
            Signal.AGUARDAR,
            50,
            "Candle sem faixa válida; decisão bloqueada.",
            False,
            snapshot.symbol,
            snapshot.timeframe,
        )

    body_ratio = abs(latest.close - latest.open) / candle_range
    close_position = (latest.close - latest.low) / candle_range
    bullish = latest.close > latest.open
    bearish = latest.close < latest.open
    confirmation = previous is not None and (
        (bullish and latest.close > previous.close)
        or (bearish and latest.close < previous.close)
    )

    body_strength = min(100.0, body_ratio * 100.0)
    if bullish:
        direction_score = 100.0
        body_score = body_strength
        close_score = close_position * 100.0
        confirmation_score = 100.0 if confirmation else 0.0
    elif bearish:
        direction_score = 0.0
        body_score = 100.0 - body_strength
        close_score = (1.0 - close_position) * 100.0
        confirmation_score = 0.0 if confirmation else 100.0
    else:
        direction_score = 50.0
        body_score = 50.0
        close_score = 50.0
        confirmation_score = 0.0

    score = (
        direction_score * 0.25
        + body_score * 0.25
        + close_score * 0.25
        + confirmation_score * 0.25
    )

    if body_ratio < 0.25:
        confirmation = False

    return SignalEngine().evaluate(
        score=round(score, 2),
        confirmed=confirmation,
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
    )
