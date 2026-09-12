from __future__ import annotations

from .methodology_observation import observe_candles
from .models import AnalysisResult, Signal
from .p122_broker_market_data import BrokerMarketDataSnapshot
from .signal_engine import SignalEngine


def evaluate_candle_snapshot(snapshot: BrokerMarketDataSnapshot) -> AnalysisResult:
    """Evaluate completed candles conservatively without broker side effects."""
    candles = snapshot.candles
    observation = observe_candles(list(candles))
    if observation is None:
        return AnalysisResult(
            Signal.AGUARDAR,
            0,
            "Sem candles suficientes para análise.",
            False,
            snapshot.symbol,
            snapshot.timeframe,
        )

    latest = observation.latest
    previous = observation.previous
    candle_range = latest.range_size
    if candle_range <= 0:
        return AnalysisResult(
            Signal.AGUARDAR,
            50,
            "Candle sem faixa válida; decisão bloqueada.",
            False,
            snapshot.symbol,
            snapshot.timeframe,
        )

    body_ratio = latest.body_ratio
    close_position = latest.close_position
    bullish = latest.direction == "ALTA"
    bearish = latest.direction == "BAIXA"
    previous_candle = candles[-2] if len(candles) >= 2 else None
    confirmation = previous_candle is not None and (
        (bullish and candles[-1].close > previous_candle.close)
        or (bearish and candles[-1].close < previous_candle.close)
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
