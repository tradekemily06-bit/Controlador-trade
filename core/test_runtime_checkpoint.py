from datetime import datetime, timezone

import pytest

from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore


def test_checkpoint_round_trip(tmp_path):
    path = tmp_path / "checkpoint.json"
    checkpoint = RuntimeCheckpoint("session-1", 4, "req-004", datetime.now(timezone.utc))
    store = RuntimeCheckpointStore(path)
    store.save(checkpoint)
    assert store.load() == checkpoint


def test_missing_checkpoint_is_empty(tmp_path):
    assert RuntimeCheckpointStore(tmp_path / "missing.json").load() is None


def test_invalid_checkpoint_fails_closed(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text('{"last_cycle": "bad"}', encoding="utf-8")
    with pytest.raises(ValueError, match="checkpoint de runtime inválido"):
        RuntimeCheckpointStore(path).load()


def test_invalid_checkpoint_rejected_on_save(tmp_path):
    store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    with pytest.raises(ValueError):
        store.save(RuntimeCheckpoint("", 0, None, datetime.now(timezone.utc)))


def test_negative_cycle_is_rejected(tmp_path):
    store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    with pytest.raises(ValueError):
        store.save(RuntimeCheckpoint("session", -1, None, datetime.now(timezone.utc)))


def test_checkpoint_atomic_failure_preserves_previous_checkpoint(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    store = RuntimeCheckpointStore(path)
    first = RuntimeCheckpoint("session", 1, "req-1", datetime(2026, 9, 18, tzinfo=timezone.utc))
    second = RuntimeCheckpoint("session", 2, "req-2", datetime(2026, 9, 18, 0, 1, tzinfo=timezone.utc))
    store.save(first)
    original = path.read_text(encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("commit failed")

    monkeypatch.setattr("core.durable_json.os.replace", fail_replace)

    with pytest.raises(OSError):
        store.save(second)

    assert path.read_text(encoding="utf-8") == original
    assert store.load() == first


def test_stale_checkpoint_cannot_overwrite_newer_checkpoint(tmp_path):
    path = tmp_path / "checkpoint.json"
    store = RuntimeCheckpointStore(path)
    newer = RuntimeCheckpoint(
        "session",
        10,
        "req-10",
        datetime(2026, 9, 18, 0, 10, tzinfo=timezone.utc),
    )
    older = RuntimeCheckpoint(
        "session",
        5,
        "req-5",
        datetime(2026, 9, 18, 0, 5, tzinfo=timezone.utc),
    )

    store.save(newer)
    store.save(older)

    assert store.load() == newer


def test_stale_writer_from_previous_session_is_fenced(tmp_path):
    path = tmp_path / "checkpoint.json"
    store = RuntimeCheckpointStore(path)
    store.save(
        RuntimeCheckpoint(
            "session-old",
            10,
            "req-old",
            datetime(2026, 9, 18, 0, 10, tzinfo=timezone.utc),
        )
    )
    store.begin_session(
        "session-new",
        updated_at=datetime(2026, 9, 18, 0, 11, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="sessão do checkpoint diverge"):
        store.save(
            RuntimeCheckpoint(
                "session-old",
                99,
                "req-old-99",
                datetime(2026, 9, 18, 0, 12, tzinfo=timezone.utc),
            )
        )

    assert store.load() == RuntimeCheckpoint(
        "session-new",
        0,
        None,
        datetime(2026, 9, 18, 0, 11, tzinfo=timezone.utc),
    )


def test_begin_session_is_idempotent_for_same_session(tmp_path):
    store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    first = store.begin_session(
        "session",
        updated_at=datetime(2026, 9, 18, 0, 10, tzinfo=timezone.utc),
    )
    second = store.begin_session(
        "session",
        updated_at=datetime(2026, 9, 18, 0, 11, tzinfo=timezone.utc),
    )

    assert second == first
    assert store.load() == first


def test_corrupted_checkpoint_cannot_be_overwritten_by_save(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text("[]", encoding="utf-8")
    store = RuntimeCheckpointStore(path)
    incoming = RuntimeCheckpoint(
        "session",
        1,
        "req-1",
        datetime(2026, 9, 18, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="checkpoint de runtime inválido"):
        store.save(incoming)

    assert path.read_text(encoding="utf-8") == "[]"


def test_corrupted_checkpoint_timestamp_cannot_be_overwritten_by_save(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text(
        '{"session_id":"session","last_cycle":1,"last_request_id":"req-1","updated_at":"not-a-timestamp"}',
        encoding="utf-8",
    )
    store = RuntimeCheckpointStore(path)
    incoming = RuntimeCheckpoint(
        "session",
        2,
        "req-2",
        datetime(2026, 9, 18, 0, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="checkpoint de runtime inválido"):
        store.save(incoming)

    assert "not-a-timestamp" in path.read_text(encoding="utf-8")


def test_naive_checkpoint_timestamp_is_rejected(tmp_path):
    store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    with pytest.raises(ValueError, match="timezone"):
        store.save(RuntimeCheckpoint("session", 1, None, datetime(2026, 9, 18, 12, 0)))
