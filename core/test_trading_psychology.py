import pytest

from core.trading_psychology import PsychologyCheckIn, PsychologyFlag, TradingPsychologyGuard


def test_revenge_and_fatigue_are_flagged_without_authorizing_trading():
    assessment = TradingPsychologyGuard().assess(
        PsychologyCheckIn(
            emotional_state="tenso",
            urge_to_trade=9,
            recent_losses=3,
            fatigue=8,
            confidence=6,
            rule_adherence=3,
        )
    )
    assert PsychologyFlag.REVENGE in assessment.flags
    assert PsychologyFlag.FOMO in assessment.flags
    assert PsychologyFlag.FATIGUE in assessment.flags
    assert PsychologyFlag.TILT in assessment.flags
    assert assessment.trading_authorized is False
    assert assessment.risk_level == "HIGH"


def test_clear_check_in_is_educational_only():
    assessment = TradingPsychologyGuard().assess(
        PsychologyCheckIn(
            emotional_state="calmo",
            urge_to_trade=2,
            recent_losses=0,
            fatigue=1,
            confidence=6,
            rule_adherence=10,
        )
    )
    assert assessment.flags == ()
    assert assessment.risk_level == "LOW"
    assert assessment.trading_authorized is False


def test_scores_outside_range_are_rejected():
    with pytest.raises(ValueError):
        TradingPsychologyGuard().assess(
            PsychologyCheckIn("calmo", urge_to_trade=11, recent_losses=0, fatigue=0, confidence=0, rule_adherence=0)
        )
