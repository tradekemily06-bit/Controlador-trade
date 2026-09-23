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


def test_corrupted_journal_is_not_overwritten_automatically(tmp_path):
    path = tmp_path / "journal.json"
    path.write_text("{not-json", encoding="utf-8")
    journal = DailyOperationJournal(path)

    try:
        journal.append(
            request_id="blocked",
            mode="DEMO",
            action="OPEN",
            symbol="EURUSD",
            signal="COMPRA",
            amount=1,
            duration_seconds=60,
            status="ACCEPTED",
            accepted=True,
            external_id="x",
            message="ok",
        )
    except OSError:
        pass
    else:
        raise AssertionError("corrupted journal must require maintenance")

    assert path.read_text(encoding="utf-8") == "{not-json"
    assert journal.summary()["storage_health"] == "CORRUPTED"
