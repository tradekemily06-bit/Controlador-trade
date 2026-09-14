from analysis.decision_record import DecisionRecord
from core.trading_psychology_history import TradingPsychologyHistory


def record(index: int, outcome: str | None, actionable: bool = True) -> DecisionRecord:
    return DecisionRecord(
        decision_id=str(index), created_at=f"2026-09-14T12:0{index}:00+00:00",
        symbol="EURUSD", timeframe="M5", signal="COMPRA" if actionable else "AGUARDAR",
        score=90, confirmed=actionable, reason="test", outcome=outcome,
    )


def test_history_derives_losses_and_repeated_entries_after_loss():
    records = (record(1, "LOSS"), record(2, "WIN"), record(3, "LOSS"), record(4, None))
    snapshot = TradingPsychologyHistory().snapshot(records)
    assert snapshot.trades_count == 4
    assert snapshot.losses == 2
    assert snapshot.wins == 1
    assert snapshot.repeated_entries_after_loss == 1
    assert snapshot.avg_seconds_between_trades is not None


def test_history_assessment_combines_history_with_context():
    records = (record(1, "LOSS"), record(2, "LOSS"), record(3, None))
    assessment = TradingPsychologyHistory().assess_history(records, urge_to_trade=9)
    patterns = {item.pattern.value for item in assessment.evidence}
    assert "REVENGE" in patterns
    assert "FOMO" in patterns
    assert assessment.trading_authorized is False
