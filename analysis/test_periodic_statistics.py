from analysis.decision_record import DecisionRecord
from analysis.statistics import summarize_periods


def make(created_at: str, outcome: str = "WIN") -> DecisionRecord:
    return DecisionRecord(
        decision_id=created_at,
        created_at=created_at,
        symbol="EURUSD",
        timeframe="5m",
        signal="COMPRA",
        score=90,
        confirmed=True,
        reason="test",
        outcome=outcome,
    )


def test_periods_use_utc_and_include_only_current_windows():
    now = __import__("datetime").datetime(2026, 9, 11, 12, 0, tzinfo=__import__("datetime").timezone.utc)
    records = [
        make("2026-09-11T11:00:00+00:00", "WIN"),
        make("2026-09-10T11:00:00+00:00", "LOSS"),
        make("2026-09-07T11:00:00+00:00", "WIN"),
        make("2026-08-31T11:00:00+00:00", "LOSS"),
    ]

    stats = summarize_periods(records, now=now)

    assert stats["daily"]["total"] == 1
    assert stats["daily"]["wins"] == 1
    assert stats["weekly"]["total"] == 3
    assert stats["weekly"]["wins"] == 2
    assert stats["monthly"]["total"] == 3
    assert stats["monthly"]["losses"] == 1


def test_periods_handle_month_and_year_boundaries():
    now = __import__("datetime").datetime(2026, 1, 2, 12, 0, tzinfo=__import__("datetime").timezone.utc)
    records = [
        make("2026-01-01T01:00:00+00:00", "WIN"),
        make("2025-12-31T23:59:59+00:00", "LOSS"),
    ]

    stats = summarize_periods(records, now=now)

    assert stats["daily"]["total"] == 1
    assert stats["monthly"]["total"] == 1
