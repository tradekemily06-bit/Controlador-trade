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

def test_checkpoint_rejects_stale_timestamp(tmp_path):
    path = tmp_path / "checkpoint.json"
    store = RuntimeCheckpointStore(path)
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    store.save(RuntimeCheckpoint("new-session", 5, "req-005", now))
    with pytest.raises(ValueError, match="mais antigo"):
        store.save(RuntimeCheckpoint("old-session", 99, "req-old", now - timedelta(seconds=1)))


def test_checkpoint_rejects_cycle_regression_within_session(tmp_path):
    path = tmp_path / "checkpoint.json"
    store = RuntimeCheckpointStore(path)
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    store.save(RuntimeCheckpoint("session", 5, "req-005", now))
    with pytest.raises(ValueError, match="regredir"):
        store.save(RuntimeCheckpoint("session", 4, "req-004", now + timedelta(seconds=1)))
