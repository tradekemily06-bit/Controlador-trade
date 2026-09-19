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


def test_checkpoint_rejects_oversized_identifier(tmp_path):
    store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    with pytest.raises(ValueError):
        store.save(RuntimeCheckpoint("x" * 257, 0, None, datetime.now(timezone.utc)))


def test_checkpoint_rejects_oversized_persisted_file(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_bytes(b"x" * (64 * 1024 + 1))
    with pytest.raises(ValueError, match="checkpoint de runtime inválido"):
        RuntimeCheckpointStore(path).load()


def test_checkpoint_rejects_symlinked_state(tmp_path):
    target = tmp_path / "target.json"
    target.write_text('{"session_id":"s","last_cycle":0,"last_request_id":null,"updated_at":"2026-09-19T00:00:00+00:00"}', encoding="utf-8")
    path = tmp_path / "checkpoint.json"
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink não suportado neste ambiente")
    with pytest.raises(ValueError, match="arquivo regular"):
        RuntimeCheckpointStore(path).load()
