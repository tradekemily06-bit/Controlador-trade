from datetime import datetime, timezone
import os

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


def test_timezone_naive_checkpoint_is_rejected(tmp_path):
    store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    with pytest.raises(ValueError, match="timezone-aware"):
        store.save(RuntimeCheckpoint("session", 1, None, datetime(2026, 1, 1)))


def test_persisted_timezone_naive_checkpoint_fails_closed(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text(
        '{"session_id":"session","last_cycle":1,"last_request_id":null,'
        '"updated_at":"2026-01-01T00:00:00"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="checkpoint de runtime inválido"):
        RuntimeCheckpointStore(path).load()


def test_checkpoint_persistence_flushes_before_atomic_replace(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    store = RuntimeCheckpointStore(path)
    calls = []
    real_fsync = os.fsync
    real_replace = os.replace

    def fsync(fd):
        calls.append("fsync")
        return real_fsync(fd)

    def replace(src, dst):
        calls.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    store.save(RuntimeCheckpoint("session", 1, None, datetime.now(timezone.utc)))

    assert calls.index("fsync") < calls.index("replace")
    assert calls.count("fsync") >= (1 if os.name == "nt" else 3)


def test_checkpoint_write_is_atomic_and_reloadable(tmp_path):
    path = tmp_path / "checkpoint.json"
    store = RuntimeCheckpointStore(path)
    checkpoint = RuntimeCheckpoint("session-1", 7, "req-7", datetime.now(timezone.utc))
    store.save(checkpoint)
    assert store.load() == checkpoint
