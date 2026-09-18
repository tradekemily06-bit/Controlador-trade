from datetime import datetime, timezone

import pytest

from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)


def test_lifecycle_survives_restart(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now, "started"))
    assert ExecutionLifecycleStore(path).get("req-1").state is ExecutionLifecycleState.PENDING


def test_unknown_blocks_implicit_transition(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now, "uncertain"))
    with pytest.raises(ValueError, match="UNKNOWN"):
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now, "accepted"))


def test_unknown_requires_explicit_reconciliation(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now))
    result = store.reconcile("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now, message="confirmed")
    assert result.state is ExecutionLifecycleState.ACCEPTED
    assert ExecutionLifecycleStore(path).get("req-1") == result


def test_invalid_persisted_state_fails_closed(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text('[{"request_id":"req-1","state":"INVALID","updated_at":"bad"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="ciclo de execução persistido inválido"):
        ExecutionLifecycleStore(path)


def test_reconciliation_requires_existing_request(tmp_path):
    with pytest.raises(ValueError, match="não encontrada"):
        ExecutionLifecycleStore(tmp_path / "lifecycle.json").reconcile(
            "missing", ExecutionLifecycleState.REJECTED, updated_at=datetime.now(timezone.utc)
        )


def test_terminal_lifecycle_state_cannot_be_changed_by_put(tmp_path):
    path = tmp_path / "lifecycle.json"
    store = ExecutionLifecycleStore(path)
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.ACCEPTED, now))

    with pytest.raises(ValueError, match="estado terminal"):
        store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.REJECTED, now))

    assert store.get("req-terminal").state is ExecutionLifecycleState.ACCEPTED


def test_duplicate_persisted_request_id_fails_closed(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text(
        '[{"request_id":"req-dup","state":"PENDING","updated_at":"2026-01-01T00:00:00+00:00"},'
        '{"request_id":"req-dup","state":"ACCEPTED","updated_at":"2026-01-01T00:01:00+00:00"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ciclo de execução persistido inválido"):
        ExecutionLifecycleStore(path)


def test_terminal_lifecycle_state_cannot_be_overwritten_by_reconciliation(tmp_path):
    path = tmp_path / "lifecycle.json"
    store = ExecutionLifecycleStore(path)
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.ACCEPTED, now))

    with pytest.raises(ValueError, match="PENDING/UNKNOWN"):
        store.reconcile("req-terminal", ExecutionLifecycleState.REJECTED, updated_at=now)

    assert store.get("req-terminal").state is ExecutionLifecycleState.ACCEPTED


def test_lifecycle_atomic_failure_does_not_publish_partial_state(tmp_path, monkeypatch):
    path = tmp_path / "lifecycle.json"
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.REJECTED, now, "rejected"))
    original = path.read_text(encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("commit failed")

    monkeypatch.setattr("core.durable_json.os.replace", fail_replace)

    with pytest.raises(OSError, match="não foi possível persistir o ciclo de execução"):
        store.put(ExecutionLifecycleRecord("req-2", ExecutionLifecycleState.PENDING, now, "pending"))

    assert path.read_text(encoding="utf-8") == original
    restored = ExecutionLifecycleStore(path)
    assert restored.get("req-1").state is ExecutionLifecycleState.REJECTED
    assert restored.get("req-2") is None


def test_two_lifecycle_instances_preserve_both_concurrent_records(tmp_path):
    from threading import Thread

    path = tmp_path / "lifecycle-race.json"
    first = ExecutionLifecycleStore(path)
    second = ExecutionLifecycleStore(path)
    now = datetime.now(timezone.utc)

    errors = []

    def put(store, request_id):
        try:
            store.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.PENDING, now, request_id))
        except Exception as exc:
            errors.append(exc)

    threads = [
        Thread(target=put, args=(first, "req-a")),
        Thread(target=put, args=(second, "req-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    restored = ExecutionLifecycleStore(path)
    assert restored.get("req-a") is not None
    assert restored.get("req-b") is not None
