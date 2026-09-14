import pytest

from core.trading_psychology_advanced import AdvancedTradingPsychology, BehavioralObservation, BehavioralPattern


def test_detects_revenge_risk_escalation_and_never_authorizes():
    profile = AdvancedTradingPsychology().assess(
        BehavioralObservation(
            recent_loss_streak=3,
            revenge_intent=True,
            urgency=8,
            risk_per_operation=2.0,
            baseline_risk=1.0,
            post_loss_risk_change=0.8,
        )
    )
    assert BehavioralPattern.REVENGE_TRADING in profile.patterns
    assert BehavioralPattern.RISK_ESCALATION in profile.patterns
    assert BehavioralPattern.LOSS_CHASING in profile.patterns
    assert profile.severity == "CRITICAL"
    assert profile.execution_authorized is False


def test_detects_overtrading_fomo_and_confirmation_seeking():
    profile = AdvancedTradingPsychology().assess(
        BehavioralObservation(
            operations=10,
            urgency=9,
            seconds_since_last_operation=10,
            repeated_same_setup=4,
            plan_adherence=5,
        )
    )
    assert BehavioralPattern.OVERTRADING in profile.patterns
    assert BehavioralPattern.FOMO in profile.patterns
    assert BehavioralPattern.IMPATIENCE in profile.patterns
    assert BehavioralPattern.CONFIRMATION_SEEKING in profile.patterns


def test_session_trend_identifies_deterioration():
    engine = AdvancedTradingPsychology()
    observations = [
        BehavioralObservation(),
        BehavioralObservation(),
        BehavioralObservation(operations=10, urgency=9, fatigue=8, rules_broken=2, plan_adherence=3),
        BehavioralObservation(operations=9, urgency=9, fatigue=8, rules_broken=2, plan_adherence=3),
    ]
    trend = engine.session_trend(observations)
    assert trend["sessions"] == 4
    assert trend["trend"] == "DETERIORATING"
    assert trend["high_risk_sessions"] >= 1


def test_rejects_invalid_behavioral_scores():
    with pytest.raises(ValueError):
        AdvancedTradingPsychology().assess(BehavioralObservation(urgency=11))
