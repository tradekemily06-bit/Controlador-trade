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


def test_terminal_states_cannot_be_reopened(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))
    for state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.REJECTED, ExecutionLifecycleState.UNKNOWN):
        with pytest.raises(ValueError, match="transição"):
            store.put(ExecutionLifecycleRecord("req-1", state, now))


def test_rejected_is_terminal(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.REJECTED, now))
    with pytest.raises(ValueError, match="transição"):
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))


def test_concurrent_store_instances_do_not_overwrite_newer_state(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    first = ExecutionLifecycleStore(path)
    second = ExecutionLifecycleStore(path)

    first.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    second = ExecutionLifecycleStore(path)
    first.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now, "accepted"))

    with pytest.raises(ValueError, match="transição"):
        second.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now, "stale writer"))

    assert ExecutionLifecycleStore(path).get("req-1").state is ExecutionLifecycleState.ACCEPTED


def test_reconcile_uses_latest_persisted_state(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    first = ExecutionLifecycleStore(path)
    first.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now))
    stale = ExecutionLifecycleStore(path)

    first.reconcile(
        "req-1",
        ExecutionLifecycleState.REJECTED,
        updated_at=now,
        message="broker confirmed rejection",
    )

    with pytest.raises(ValueError, match="somente UNKNOWN/PENDING"):
        stale.reconcile(
            "req-1",
            ExecutionLifecycleState.ACCEPTED,
            updated_at=now,
            message="stale reconciliation",
        )


def test_persisted_lifecycle_rejects_duplicate_request_id(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text(
        '[{"request_id":"dup","state":"PENDING","updated_at":"2026-01-01T00:00:00+00:00"},'
        '{"request_id":"dup","state":"UNKNOWN","updated_at":"2026-01-01T00:00:01+00:00"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ciclo de execução persistido inválido"):
        ExecutionLifecycleStore(path)
