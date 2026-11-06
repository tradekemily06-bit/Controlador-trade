from datetime import datetime, timedelta, timezone

import pytest

from execution.timed_exit_store import TimedExitStore


def test_timed_exit_store_persists_schedule_and_restores_due_work(tmp_path):
    path = tmp_path / "timed-exits.json"
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    store = TimedExitStore(path)
    record = store.schedule(
        request_id="request-1",
        cycle_id="cycle-1",
        external_id="12345",
        account_fingerprint="a" * 32,
        delay_seconds=60,
        now=now,
    )

    restored = TimedExitStore(path)
    assert restored.record_for("request-1") == record
    assert restored.due(now=now + timedelta(seconds=59)) == ()
    assert restored.due(now=now + timedelta(seconds=60)) == (record,)


def test_timed_exit_store_schedule_is_idempotent_but_rejects_identity_change(tmp_path):
    store = TimedExitStore(tmp_path / "timed-exits.json")
    first = store.schedule(
        request_id="request-1",
        cycle_id="cycle-1",
        external_id="12345",
        account_fingerprint="a" * 32,
        delay_seconds=60,
    )
    again = store.schedule(
        request_id="request-1",
        cycle_id="cycle-1",
        external_id="12345",
        account_fingerprint="a" * 32,
        delay_seconds=120,
    )
    assert again == first

    with pytest.raises(ValueError):
        store.schedule(
            request_id="request-1",
            cycle_id="cycle-1",
            external_id="99999",
            account_fingerprint="a" * 32,
            delay_seconds=60,
        )


def test_timed_exit_store_requires_account_fingerprint_and_timezone(tmp_path):
    store = TimedExitStore(tmp_path / "timed-exits.json")
    with pytest.raises(ValueError):
        store.schedule(
            request_id="request-1",
            cycle_id="cycle-1",
            external_id="12345",
            account_fingerprint="",
            delay_seconds=60,
        )
    with pytest.raises(ValueError):
        store.schedule(
            request_id="request-2",
            cycle_id="cycle-2",
            external_id="12346",
            account_fingerprint="a" * 32,
            delay_seconds=60,
            now=datetime(2026, 11, 5, 12),
        )


def test_timed_exit_store_retries_then_marks_closed(tmp_path):
    store = TimedExitStore(tmp_path / "timed-exits.json")
    store.schedule(
        request_id="request-1",
        cycle_id="cycle-1",
        external_id="12345",
        account_fingerprint="a" * 32,
        delay_seconds=1,
        now=datetime(2026, 11, 5, 12, tzinfo=timezone.utc),
    )
    retry = store.retry_later("request-1", message="MT5 inconclusivo")
    assert retry.state == "SCHEDULED"
    assert retry.attempts == 1
    closed = store.mark_closed("request-1", message="MT5 confirmou CLOSED")
    assert closed.state == "CLOSED"
    assert store.due(now=datetime.now(timezone.utc) + timedelta(days=1)) == ()
