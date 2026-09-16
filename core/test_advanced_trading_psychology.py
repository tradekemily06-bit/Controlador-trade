from core.advanced_trading_psychology import AdvancedTradingPsychology, BehavioralPattern, TradingBehaviorSnapshot


def test_detects_compound_revenge_and_tilt():
    result = AdvancedTradingPsychology().assess(TradingBehaviorSnapshot(losses=3, consecutive_losses=3, repeated_entries_after_loss=2, rule_breaks=2, urge_to_trade=9))
    patterns = {item.pattern for item in result.evidence}
    assert BehavioralPattern.REVENGE in patterns
    assert BehavioralPattern.TILT in patterns
    assert result.risk_level == "HIGH"
    assert result.trading_authorized is False


def test_detects_risk_escalation_and_overconfidence():
    result = AdvancedTradingPsychology().assess(TradingBehaviorSnapshot(risk_before=50, risk_after=70, confidence=10, rule_breaks=1))
    patterns = {item.pattern for item in result.evidence}
    assert BehavioralPattern.RISK_ESCALATION in patterns
    assert BehavioralPattern.OVERCONFIDENCE in patterns
    assert result.trading_authorized is False


def test_detects_overtrading_impatience_and_fatigue():
    result = AdvancedTradingPsychology().assess(TradingBehaviorSnapshot(trades_count=15, avg_seconds_between_trades=30, fatigue=8))
    patterns = {item.pattern for item in result.evidence}
    assert BehavioralPattern.OVERTRADING in patterns
    assert BehavioralPattern.IMPATIENCE in patterns
    assert BehavioralPattern.FATIGUE in patterns


def test_trend_identifies_recurring_patterns_and_direction():
    engine = AdvancedTradingPsychology()
    a = engine.assess(TradingBehaviorSnapshot(urge_to_trade=9, trades_count=1))
    b = engine.assess(TradingBehaviorSnapshot(urge_to_trade=9, trades_count=1, fatigue=8))
    c = engine.assess(TradingBehaviorSnapshot())
    trend = engine.trend((a, b, c))
    assert trend.sessions == 3
    assert BehavioralPattern.FOMO in trend.recurring_patterns
    assert trend.direction == "IMPROVING"


def test_invalid_scores_are_rejected():
    try:
        AdvancedTradingPsychology().assess(TradingBehaviorSnapshot(fatigue=11))
    except ValueError as exc:
        assert "fatigue" in str(exc)
    else:
        raise AssertionError("invalid psychology score should fail")
