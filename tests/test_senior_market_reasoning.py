from datetime import datetime, timedelta, timezone

from data.models import Candle
from core.integrated_market_reading import IntegratedMarketReader, ReadingStatus
from core.senior_market_reasoning import ReasoningPosture, SeniorMarketReasoner
from core.temporal_market_context import TemporalMarketContextEngine


def candles_for_context() -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = [
        (100, 103, 99, 102),
        (102, 105, 101, 104),
        (104, 107, 103, 106),
        (106, 110, 105, 109),
    ]
    return [
        Candle(timestamp=start + timedelta(minutes=i), open=o, high=h, low=l, close=c, volume=100)
        for i, (o, h, l, c) in enumerate(values)
    ]


def test_senior_reasoning_joins_history_present_and_conditional_scenarios():
    candles = candles_for_context()
    reading = IntegratedMarketReader().read(candles)
    temporal = TemporalMarketContextEngine().analyze(candles)
    assessment = SeniorMarketReasoner().assess(candles, reading, temporal)

    assert assessment.execution_authorized is False
    assert assessment.observations
    assert assessment.questions
    assert temporal.historical
    assert temporal.present
    assert temporal.scenarios
    assert "histórico" in assessment.context_statement


def test_conflicting_reading_requires_reassessment_not_signal_counting():
    candles = candles_for_context()
    reading = IntegratedMarketReader().read(candles)
    conflicting = reading.__class__(
        status=ReadingStatus.CONFLICTING,
        observations=reading.observations,
        supporting=("trend-context",),
        contradicting=("candle-body",),
        conflicts=("evidência conflitante",),
        possible_false_breakout=False,
        unanswered_questions=reading.unanswered_questions,
    )
    temporal = TemporalMarketContextEngine().analyze(candles)
    assessment = SeniorMarketReasoner().assess(candles, conflicting, temporal)

    assert assessment.posture is ReasoningPosture.REASSESS
    assert "Não escolher o lado vencedor" in " ".join(assessment.avoid_assumptions)
    assert any(q.category == "conflito" for q in assessment.questions)
    assert assessment.execution_authorized is False


def test_insufficient_context_preserves_uncertainty():
    candles = candles_for_context()[:1]
    reading = IntegratedMarketReader().read(candles)
    temporal = TemporalMarketContextEngine().analyze(candles)
    assessment = SeniorMarketReasoner().assess(candles, reading, temporal)

    assert assessment.posture is ReasoningPosture.INSUFFICIENT
    assert assessment.uncertainty
    assert assessment.execution_authorized is False
