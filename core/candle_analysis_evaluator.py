from __future__ import annotations

from .models import AnalysisResult, Signal
from .p122_broker_market_data import BrokerMarketDataSnapshot


def evaluate_candle_snapshot(snapshot: BrokerMarketDataSnapshot) -> AnalysisResult:
    """Evaluate a completed-candle snapshot with conservative price structure.

    This deterministic layer never accesses a broker, places orders, or changes
    the existing SignalEngine thresholds. It is suitable for DEMO analysis.
    """
    candles = snapshot.candles
    if not candles:
        return AnalysisResult(Signal.AGUARDAR, 0, "Sem candles suficientes para análise.", False, snapshot.symbol, snapshot.timeframe)

    latest = candles[-1]
    previous = candles[-2] if len(candles) >= 2 else None
    candle_range = latest.high - latest.low
    if candle_range <= 0:
        return AnalysisResult(Signal.AGUARDAR, 50, "Candle sem faixa válida; decisão bloqueada.", False, snapshot.symbol, snapshot.timeframe)

    body_ratio = abs(latest.close - latest.open) / candle_range
    close_position = (latest.close - latest.low) / candle_range
    bullish = latest.close > latest.open
    bearish = latest.close < latest.open
    confirmation = previous is not None and ((bullish and latest.close > previous.close) or (bearish and latest.close < previous.close))

    direction_score = 100.0 if bullish else 0.0 if bearish else 50.0
    body_score = min(100.0, body_ratio * 100.0)
    close_score = close_position * 100.0
    confirmation_score = 100.0 if confirmation else 0.0
    if bearish:
        close_score = 100.0 - close_score

    score = direction_score * 0.25 + body_score * 0.25 + close_score * 0.25 + confirmation_score * 0.25

    if not confirmation or body_ratio < 0.25:
        signal = Signal.AGUARDAR
        reason = "Estrutura sem confirmação suficiente no fechamento."
    elif bullish and score >= 70:
        signal = Signal.COMPRA
        reason = "Candle comprador com corpo e confirmação favoráveis."
    elif bearish and score <= 30:
        signal = Signal.VENDA
        reason = "Candle vendedor com corpo e confirmação favoráveis."
    else:
        signal = Signal.AGUARDAR
        reason = "Condições mistas; aguardando confirmação mais forte."

    return AnalysisResult(signal, round(score, 2), reason, confirmation, snapshot.symbol, snapshot.timeframe)
