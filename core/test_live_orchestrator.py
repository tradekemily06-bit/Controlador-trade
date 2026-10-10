from datetime import datetime, timezone

import pytest

from analysis.pipeline import StrategyPipeline
from core.decision_engine import DecisionEngine, FinalDecision
from core.market_context import MarketContext, MarketContextResult, MarketDirection
from core.operational_state import OperationalState
from core.signal_quality import SignalQualityEvaluator
from core.risk_manager import RiskManager
from data.feed import MarketDataFeed, MarketDataRequest
from data.models import Candle
from core.live_orchestrator import TradingOrchestrator
from core.indicator_sources import ExternalIndicatorReading, IndicatorSourceKind


class Provider:
    def __init__(self, candles):
        self.candles = candles

    def fetch(self, request):
        return self.candles


def make_candles():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(base, 100, 101, 99, 100, 10),
        Candle(base.replace(minute=1), 100, 102, 100, 102, 12),
        Candle(base.replace(minute=2), 102, 103, 101, 103, 14),
    ]


def make_orchestrator(data):
    feed = MarketDataFeed(Provider(data), source="test")
    return TradingOrchestrator(
        feed=feed,
        pipeline=StrategyPipeline(),
        decision_engine=DecisionEngine(RiskManager()),
        quality_evaluator=SignalQualityEvaluator(),
    )


def favorable():
    return MarketContextResult(
        context=MarketContext.FAVORAVEL,
        score=100.0,
        reason="teste",
        direction=MarketDirection.ALTA,
    )


def state():
    return OperationalState(trades_today=0, consecutive_losses=0)


def test_orchestrator_preserves_full_pipeline_without_execution():
    result = make_orchestrator(make_candles()).evaluate(
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
    result = make_orchestrator(make_candles()).evaluate(
        MarketDataRequest("TEST", "1m", 3),
        operational_state=None,
        market_context=None,
    )
    assert result.decision.decision == FinalDecision.AGUARDAR
    assert result.executable is False


def test_orchestrator_rejects_empty_feed_before_analysis():
    with pytest.raises(ValueError, match="no candles"):
        make_orchestrator([]).evaluate(
            MarketDataRequest("TEST", "1m", 3),
            operational_state=state(),
            market_context=favorable(),
        )


def test_orchestrator_uses_feed_limit_after_validation():
    result = make_orchestrator(make_candles()).evaluate(
        MarketDataRequest("TEST", "1m", 2),
        operational_state=state(),
        market_context=favorable(),
    )
    assert len(result.market_data.candles) == 2


def test_orchestrator_derives_market_context_from_same_feed():
    result = make_orchestrator(make_candles()).evaluate(
        MarketDataRequest("TEST", "1m", 3),
        operational_state=state(),
        market_context=None,
        confirmed=True,
    )
    assert result.market_data.candles
    assert result.snapshot.market_context is not None


def test_orchestrator_builds_senior_context_from_same_fetched_candles():
    candles = make_candles()
    captured = []

    def builder(observed_candles, operational_state):
        captured.append((tuple(observed_candles), operational_state))
        return None

    orchestrator = TradingOrchestrator(
        feed=MarketDataFeed(Provider(candles), source="test"),
        pipeline=StrategyPipeline(),
        decision_engine=DecisionEngine(RiskManager()),
        quality_evaluator=SignalQualityEvaluator(),
        senior_context_builder=builder,
    )
    result = orchestrator.evaluate(
        MarketDataRequest("TEST", "1m", 3),
        operational_state=state(),
        market_context=favorable(),
    )
    assert len(captured) == 1
    assert captured[0][0] == result.market_data.candles
    assert captured[0][1] == state()



def test_orchestrator_exposes_indicator_evidence_from_same_candle_snapshot():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for index in range(40):
        close = 100.0 + index * 0.25
        previous = 100.0 + max(0, index - 1) * 0.25
        candles.append(Candle(
            base.replace(minute=index),
            previous,
            max(previous, close) + 0.5,
            min(previous, close) - 0.5,
            close,
            100.0,
        ))
    result = make_orchestrator(candles).evaluate(
        MarketDataRequest("TEST", "1m", 40),
        operational_state=state(),
        market_context=favorable(),
        confirmed=True,
    )

    assert result.indicator_evidence is not None
    assert result.indicator_evidence.candles_used == 40
    assert result.indicator_evidence.candle_timestamp == result.market_data.candles[-1].timestamp
    assert result.indicator_evidence.source == "test:CONTROLADOR_CALCULADO"
    # Evidence remains descriptive and cannot silently change the decision pipeline.
    assert result.snapshot.decision == result.decision.decision


def test_orchestrator_reports_indicators_unavailable_when_history_is_short():
    result = make_orchestrator(make_candles()).evaluate(
        MarketDataRequest("TEST", "1m", 3),
        operational_state=state(),
        market_context=favorable(),
    )
    assert result.indicator_evidence is None



def test_orchestrator_accepts_fresh_external_indicator_evidence_without_changing_decision():
    class ProviderWithIndicators:
        def read(self, *, symbol, timeframe, now=None):
            return ExternalIndicatorReading(
                provider="MT5 native indicator bridge",
                source_kind=IndicatorSourceKind.MT5_NATIVE,
                symbol=symbol,
                timeframe=timeframe,
                observed_at=now,
                candle_timestamp=now.replace(second=0, microsecond=0),
                values={"rsi_14": 58.0, "macd": 0.001},
                bias="BULLISH",
            )

    orchestrator = TradingOrchestrator(
        feed=MarketDataFeed(Provider(make_candles()), source="test"),
        pipeline=StrategyPipeline(),
        decision_engine=DecisionEngine(RiskManager()),
        quality_evaluator=SignalQualityEvaluator(),
        indicator_provider=ProviderWithIndicators(),
    )
    result = orchestrator.evaluate(
        MarketDataRequest("TEST", "1m", 3),
        operational_state=state(),
        market_context=favorable(),
    )

    assert result.external_indicator_status == "AVAILABLE_EVIDENCE_ONLY"
    assert result.external_indicator_reading is not None
    assert result.external_indicator_reading.values["rsi_14"] == 58.0
    assert result.snapshot.decision == result.decision.decision


def test_orchestrator_rejects_external_indicator_symbol_mismatch():
    class MismatchedProvider:
        def read(self, *, symbol, timeframe, now=None):
            return ExternalIndicatorReading(
                provider="external site",
                source_kind=IndicatorSourceKind.EXTERNAL_SITE,
                symbol="GBPUSD",
                timeframe=timeframe,
                observed_at=now,
                candle_timestamp=now.replace(second=0, microsecond=0),
                values={"rsi_14": 58.0},
            )

    orchestrator = TradingOrchestrator(
        feed=MarketDataFeed(Provider(make_candles()), source="test"),
        pipeline=StrategyPipeline(),
        decision_engine=DecisionEngine(RiskManager()),
        quality_evaluator=SignalQualityEvaluator(),
        indicator_provider=MismatchedProvider(),
    )
    result = orchestrator.evaluate(
        MarketDataRequest("TEST", "1m", 3),
        operational_state=state(),
        market_context=favorable(),
    )
    assert result.external_indicator_status == "REJECTED_SYMBOL_OR_TIMEFRAME_MISMATCH"
    assert result.external_indicator_reading is None
