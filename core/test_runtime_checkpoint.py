from datetime import datetime, timezone
from multiprocessing import Process, Queue

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


def _save_checkpoint_in_process(path, cycle, queue):
    try:
        RuntimeCheckpointStore(path).save(
            RuntimeCheckpoint(
                f"session-{cycle}",
                cycle,
                f"request-{cycle}",
                datetime.now(timezone.utc),
            )
        )
    except Exception as exc:
        queue.put(type(exc).__name__)
    else:
        queue.put("OK")


def test_checkpoint_concurrent_writes_never_publish_partial_json(tmp_path):
    path = tmp_path / "checkpoint-concurrent.json"
    queue = Queue()
    processes = [
        Process(target=_save_checkpoint_in_process, args=(path, cycle, queue))
        for cycle in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)

    results = [queue.get(timeout=5) for _ in processes]
    assert results == ["OK"] * len(processes)

    checkpoint = RuntimeCheckpointStore(path).load()
    assert checkpoint is not None
    assert checkpoint.session_id.startswith("session-")
    assert checkpoint.last_cycle in range(4)
