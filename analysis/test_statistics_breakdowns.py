from analysis.decision_record import DecisionRecord
from analysis.statistics import summarize_breakdowns


def make(decision_id: str, symbol: str | None, timeframe: str | None, outcome: str) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        created_at="2026-09-11T12:00:00+00:00",
        symbol=symbol,
        timeframe=timeframe,
        signal="COMPRA",
        score=90,
        confirmed=True,
        reason="test",
        outcome=outcome,
    )


def test_breakdowns_group_by_symbol_and_timeframe():
    stats = summarize_breakdowns(
        [
            make("1", "EURUSD", "5m", "WIN"),
            make("2", "EURUSD", "5m", "LOSS"),
            make("3", "GBPUSD", "1m", "WIN"),
        ]
    )

    assert stats["symbols"]["EURUSD"]["total"] == 2
    assert stats["symbols"]["EURUSD"]["win_rate"] == 50.0
    assert stats["symbols"]["GBPUSD"]["wins"] == 1
    assert stats["timeframes"]["5m"]["total"] == 2
    assert stats["timeframes"]["1m"]["wins"] == 1


def test_breakdowns_keep_missing_dimensions_explicit():
    stats = summarize_breakdowns([make("1", None, None, "OPEN")])

    assert stats["symbols"]["UNKNOWN"]["open"] == 1
    assert stats["timeframes"]["UNKNOWN"]["open"] == 1
