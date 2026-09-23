from datetime import datetime, timezone

from core.daily_operation_journal import DailyOperationJournal


def test_daily_journal_persists_without_becoming_execution_authority(tmp_path):
    path = tmp_path / "journal.json"
    journal = DailyOperationJournal(path)
    journal.append(
        request_id="demo-1",
        mode="DEMO",
        action="OPEN",
        symbol="EURUSD",
        signal="COMPRA",
        amount=1,
        duration_seconds=60,
        status="ACCEPTED",
        accepted=True,
        external_id="mt5-123",
        message="ok",
        timestamp=datetime(2026, 9, 23, tzinfo=timezone.utc),
    )

    reloaded = DailyOperationJournal(path)
    entries = reloaded.entries()
    assert len(entries) == 1
    assert entries[0].external_id == "mt5-123"
    assert reloaded.summary()["accepted"] == 1
    assert "execution_authority" not in entries[0].__dict__
