from datetime import datetime, timedelta, timezone

from core.integrated_market_reading import IntegratedMarketReader
from core.senior_experience_profile import SeniorExperienceProfile
from core.senior_market_reasoning import SeniorMarketReasoner
from core.temporal_market_context import TemporalMarketContextEngine
from data.models import Candle


def candles():
    base = datetime(2026, 9, 13, tzinfo=timezone.utc)
    return [
        Candle(base + timedelta(minutes=i), 100 + i, 102 + i, 99 + i, 101 + i, 1000 + i)
        for i in range(5)
    ]


def test_reasoner_has_senior_profile_before_first_user_day():
    reasoner = SeniorMarketReasoner()
    assert reasoner.experience_profile.experience_years == 45
    assert reasoner.experience_profile.first_day_with_user is True
    assert reasoner.experience_profile.experience_resets_on_assignment is False


def test_reasoner_keeps_professional_posture_separate_from_execution_authority():
    values = candles()
    reading = IntegratedMarketReader().read(values)
    temporal = TemporalMarketContextEngine().analyze(values)
    assessment = SeniorMarketReasoner(
        SeniorExperienceProfile(experience_years=45, newly_assigned_to_user=True)
    ).assess(values, reading, temporal)
    assert assessment.execution_authorized is False
    assert "histórico" in assessment.context_statement
    assert assessment.questions
