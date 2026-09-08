from datetime import datetime, timedelta

from core.decision_engine import DecisionEngine, FinalDecision
from core.market_context import MarketContextEngine
from core.market_direction import MarketDirection
from core.models import AnalysisResult, Signal
from core.operational_state import OperationalState
from core.risk_manager import RiskManager
from core.market_data import Candle


def candles_alta():
    base = datetime(2026, 1, 1)
    return [
        Candle(base, 100, 101, 99, 100, 100),
        Candle(base + timedelta(minutes=5), 100, 102, 100, 101, 100),
        Candle(base + timedelta(minutes=10), 101, 103, 101, 102, 200),
    ]


def state(*, realized_pnl=0, trades_today=0, consecutive_losses=0):
    return OperationalState(
        realized_pnl=realized_pnl,
        trades_today=trades_today,
        consecutive_losses=consecutive_losses,
    )


def test_buy_with_favorable_context_executes():
    context = MarketContextEngine().evaluate_from_candles(
        candles=candles_alta()
    )
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=80,
        reason="Sinal confirmado.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=context,
        operational_state=state(),
    )
    assert result.decision == FinalDecision.EXECUTAR


def test_unfavorable_context_waits():
    context = MarketContextEngine().evaluate(
        trend_strength=20,
        volatility_quality=20,
        liquidity_quality=20,
        direction=MarketDirection.ALTA,
    )
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=80,
        reason="Sinal confirmado.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=context,
        operational_state=state(),
    )
    assert result.decision == FinalDecision.AGUARDAR


def test_risk_blocks_execution():
    context = MarketContextEngine().evaluate(
        trend_strength=100,
        volatility_quality=100,
        liquidity_quality=100,
        direction=MarketDirection.ALTA,
    )
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=90,
        reason="Sinal confirmado.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager(daily_loss_limit=100)).evaluate(
        analysis=analysis,
        market_context=context,
        operational_state=state(realized_pnl=-100),
    )
    assert result.decision == FinalDecision.BLOQUEAR


def test_wrong_direction_waits():
    context = MarketContextEngine().evaluate(
        trend_strength=100,
        volatility_quality=100,
        liquidity_quality=100,
        direction=MarketDirection.BAIXA,
    )
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=90,
        reason="Sinal confirmado.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=context,
        operational_state=state(),
    )
    assert result.decision == FinalDecision.AGUARDAR


def test_unconfirmed_signal_waits():
    analysis = AnalysisResult(
        signal=Signal.AGUARDAR,
        score=90,
        reason="Aguardando confirmação.",
        confirmed=False,
    )
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        operational_state=state(),
    )
    assert result.decision == FinalDecision.AGUARDAR


def test_no_execution_without_operational_state():
    context = MarketContextEngine().evaluate(
        trend_strength=100,
        volatility_quality=100,
        liquidity_quality=100,
        direction=MarketDirection.ALTA,
    )
    analysis = AnalysisResult(
        signal=Signal.COMPRA,
        score=100,
        reason="Sinal confirmado.",
        confirmed=True,
    )
    result = DecisionEngine(RiskManager()).evaluate(
        analysis=analysis,
        market_context=context,
    )
    assert result.decision == FinalDecision.AGUARDAR
