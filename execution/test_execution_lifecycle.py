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


def test_terminal_state_cannot_be_overwritten(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.ACCEPTED, now))
    with pytest.raises(ValueError, match="terminal"):
        store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.PENDING, now))
    with pytest.raises(ValueError, match="terminal"):
        store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.REJECTED, now))


def test_pending_cannot_be_written_twice(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-pending", ExecutionLifecycleState.PENDING, now))
    with pytest.raises(ValueError, match="PENDING"):
        store.put(ExecutionLifecycleRecord("req-pending", ExecutionLifecycleState.PENDING, now))


def test_stale_lifecycle_instance_reloads_before_read(tmp_path):
    path = tmp_path / "lifecycle.json"
    first = ExecutionLifecycleStore(path)
    second = ExecutionLifecycleStore(path)
    now = datetime.now(timezone.utc)
    first.put(ExecutionLifecycleRecord("req-shared", ExecutionLifecycleState.PENDING, now))
    assert second.get("req-shared").state is ExecutionLifecycleState.PENDING


def test_reconciliation_cannot_mutate_terminal_state(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.REJECTED, now))
    with pytest.raises(ValueError, match="somente PENDING ou UNKNOWN"):
        store.reconcile("req-terminal", ExecutionLifecycleState.ACCEPTED, updated_at=now)


def test_lifecycle_rejects_oversized_request_id_and_message(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        store.put(ExecutionLifecycleRecord("x" * 129, ExecutionLifecycleState.PENDING, now))
    with pytest.raises(ValueError):
        store.put(ExecutionLifecycleRecord("req", ExecutionLifecycleState.PENDING, now, "x" * 4097))
