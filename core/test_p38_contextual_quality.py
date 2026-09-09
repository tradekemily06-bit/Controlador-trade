from datetime import datetime, timezone

import pytest

from core.models import AnalysisResult, Signal
from core.p36_market_context import MarketContext, NewsEvent, NewsImpact
from core.p37_market_context import ImpactCounts, MarketContextSnapshot, SymbolMarketContext
from core.p38_contextual_quality import ContextualSignalQualityEvaluator
from core.signal_quality import SignalQualityEvaluator


def _quality():
    analysis = AnalysisResult(Signal.COMPRA, 90, "confirmed", True, "BTCUSD", "5m")
    return SignalQualityEvaluator().evaluate(analysis)


def _context():
    event = NewsEvent(
        title="Macro release",
        source="wire",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        symbols=("BTCUSD",),
        impact=NewsImpact.HIGH,
    )
    return MarketContextSnapshot((SymbolMarketContext("BTCUSD", 1, ImpactCounts(high=1), (event,)),))


def test_preserves_base_quality_and_declared_impact():
    result = ContextualSignalQualityEvaluator().evaluate("btcusd", _quality(), _context())
    assert result.symbol == "BTCUSD"
    assert result.base_quality.score == 80
    assert result.event_count == 1
    assert result.high_impact_events == 1


def test_missing_symbol_is_valid_and_does_not_invent_context():
    result = ContextualSignalQualityEvaluator().evaluate("ETHUSD", _quality(), _context())
    assert result.event_count == 0
    assert result.high_impact_events == 0


def test_invalid_inputs_fail_closed():
    evaluator = ContextualSignalQualityEvaluator()
    with pytest.raises(ValueError):
        evaluator.evaluate("", _quality(), _context())
    with pytest.raises(ValueError):
        evaluator.evaluate("BTCUSD", object(), _context())
    with pytest.raises(ValueError):
        evaluator.evaluate("BTCUSD", _quality(), object())


def test_duplicate_symbol_summaries_are_rejected():
    context = MarketContextSnapshot(
        (
            SymbolMarketContext("BTCUSD", 0, ImpactCounts(), ()),
            SymbolMarketContext("BTCUSD", 0, ImpactCounts(), ()),
        )
    )
    with pytest.raises(ValueError):
        ContextualSignalQualityEvaluator().evaluate("BTCUSD", _quality(), context)


def test_p36_market_context_can_be_constructed_without_inference():
    event = NewsEvent(
        title="Fact",
        source="source",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        symbols=("BTCUSD",),
        impact=NewsImpact.UNKNOWN,
    )
    assert MarketContext(events=(event,))
