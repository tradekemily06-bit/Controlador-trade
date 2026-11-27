from analysis.decision_record import DecisionRecord
from analysis.statistics import summarize


def make(outcome, actionable=True):
    return DecisionRecord(
        decision_id=outcome,
        created_at="2026-09-10T00:00:00+00:00",
        symbol="EURUSD",
        timeframe="M5",
        signal="COMPRA" if actionable else "AGUARDAR",
        score=80 if actionable else 50,
        confirmed=actionable,
        reason="test",
        outcome=outcome,
    )


def test_summarize_counts_and_win_rate():
    stats = summarize([make("WIN"), make("LOSS"), make("WIN"), make("DRAW"), make("OPEN"), make("VOID", False)])

    assert stats.total == 6
    assert stats.actionable == 5
    assert stats.wins == 2
    assert stats.losses == 1
    assert stats.draws == 1
    assert stats.open == 1
    assert stats.closed == 3
    assert stats.win_rate == 2 / 3 * 100
    assert stats.win_rate_status == "AVAILABLE"


def test_empty_history_has_unavailable_win_rate():
    stats = summarize([])
    assert stats.closed == 0
    assert stats.win_rate is None
    assert stats.win_rate_status == "INSUFFICIENT_CLOSED_SAMPLE"


def test_open_and_draw_only_history_has_unavailable_win_rate():
    stats = summarize([make("OPEN"), make("DRAW")])
    assert stats.closed == 0
    assert stats.win_rate is None
    assert stats.win_rate_status == "INSUFFICIENT_CLOSED_SAMPLE"
