from datetime import datetime, timezone

import pytest

from analysis.pipeline import StrategyPipeline
from core.decision_engine import DecisionEngine, FinalDecision
from core.market_context import MarketContext, MarketContextResult, MarketDirection
from core.operational_state import OperationalState
from core.signal_quality import SignalQualityEvaluator
from core.risk_manager import RiskManager
from core.models import Signal
from data.feed import MarketDataFeed, MarketDataRequest
from data.models import Candle
from core.live_orchestrator import TradingOrchestrator


class Provider:
    def __init__(self, candles):
        self.candles = candles

    def fetch(self, request):
        return self.candles


def candles():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(base, 100, 101, 99, 100, 10),
        Candle(base.replace(minute=1), 100, 102, 100, 102, 12),
        Candle(base.replace(minute=2), 102, 103, 101, 103, 14),
    ]


def orchestrator(data):
    feed = MarketDataFeed(Provider(data), source="test")
    return TradingOrchestrator(
        feed=feed,
        pipeline=StrategyPipeline(),
        decision_engine=DecisionEngine(RiskManager()),
        quality_evaluator=SignalQualityEvaluator(),
    )


def favorable():
    return MarketContextResult(MarketContext.FAVORAVEL, MarketDirection.ALTA, 1.0)


def state():
    return OperationalState(trades_today=0, consecutive_losses=0)


def test_orchestrator_preserves_full_pipeline_without_execution():
    result = orchestrator(candles()).evaluate(
        MarketDataRequest("TEST", "1m", 3),
        operational_state=state(),
        market_context=favorable(),
        confirmed=True,
    )
    assert result.market_data.source == "test"
    assert result.analysis.symbol == "TEST"
    assert result.snapshot.signal == result.analysis.signal.value
    assert result.snapshot.decision == result.decision.decision
    assert result.timestamp.tzinfo is not None


def test_orchestrator_never_executes_an_order():
    result = orchestrator(candles()).evaluate(
        MarketDataRequest("TEST", "1m", 3),
        operational_state=None,
        market_context=None,
    )
    assert result.decision.decision == FinalDecision.AGUARDAR
    assert result.executable is False


def test_orchestrator_rejects_empty_feed_before_analysis():
    with pytest.raises(ValueError, match="vazios"):
        orchestrator([]).evaluate(
            MarketDataRequest("TEST", "1m", 3),
            operational_state=state(),
            market_context=favorable(),
        )


def test_orchestrator_uses_feed_limit_after_validation():
    result = orchestrator(candles()).evaluate(
        MarketDataRequest("TEST", "1m", 2),
        operational_state=state(),
        market_context=favorable(),
    )
    assert len(result.market_data.candles) == 2
