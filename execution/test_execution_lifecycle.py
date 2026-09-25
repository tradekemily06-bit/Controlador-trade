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


def test_stale_lifecycle_instances_preserve_each_other_updates(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    first = ExecutionLifecycleStore(path)
    second = ExecutionLifecycleStore(path)
    first.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now, "first"))
    second.put(ExecutionLifecycleRecord("req-2", ExecutionLifecycleState.PENDING, now, "second"))
    restored = ExecutionLifecycleStore(path)
    assert restored.get("req-1").state is ExecutionLifecycleState.PENDING
    assert restored.get("req-2").state is ExecutionLifecycleState.PENDING

def test_persistence_boundary_rejects_all_terminal_backtracking(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("accepted", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("accepted", ExecutionLifecycleState.ACCEPTED, now))
    with pytest.raises(ValueError, match="transição inválida"):
        store.put(ExecutionLifecycleRecord("accepted", ExecutionLifecycleState.REJECTED, now))

    store.put(ExecutionLifecycleRecord("rejected", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("rejected", ExecutionLifecycleState.REJECTED, now))
    with pytest.raises(ValueError, match="transição inválida"):
        store.put(ExecutionLifecycleRecord("rejected", ExecutionLifecycleState.ACCEPTED, now))


def test_reconciliation_cannot_bypass_non_unknown_state(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    with pytest.raises(ValueError, match="exige estado UNKNOWN"):
        store.reconcile("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now)
