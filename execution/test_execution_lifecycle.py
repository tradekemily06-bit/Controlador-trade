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


def test_stale_store_instances_do_not_lose_lifecycle_updates(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    first = ExecutionLifecycleStore(path)
    second = ExecutionLifecycleStore(path)

    first.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    second.put(ExecutionLifecycleRecord("req-2", ExecutionLifecycleState.PENDING, now))

    restored = ExecutionLifecycleStore(path)
    assert {r.request_id for r in restored.records()} == {"req-1", "req-2"}


def test_unknown_blocks_implicit_transition(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now, "uncertain"))
    with pytest.raises(ValueError, match="UNKNOWN"):
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now, "accepted"))


def test_terminal_lifecycle_cannot_be_rewound(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))
    with pytest.raises(ValueError, match="transição de lifecycle inválida"):
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))

    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-2", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-2", ExecutionLifecycleState.REJECTED, now))
    with pytest.raises(ValueError, match="transição de lifecycle inválida"):
        store.put(ExecutionLifecycleRecord("req-2", ExecutionLifecycleState.UNKNOWN, now))


def test_unknown_requires_explicit_reconciliation(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now))
    result = store.reconcile("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now, message="confirmed")
    assert result.state is ExecutionLifecycleState.ACCEPTED
    assert ExecutionLifecycleStore(path).get("req-1") == result


def test_project_terminal_repairs_pending_and_is_idempotent(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.project_terminal("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now, message="repair")
    assert store.get("req-1").state is ExecutionLifecycleState.ACCEPTED
    store.project_terminal("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now, message="repair-again")
    with pytest.raises(ValueError, match="conflita"):
        store.project_terminal("req-1", ExecutionLifecycleState.REJECTED, updated_at=now)


def test_reconciliation_cannot_rewrite_terminal_state(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))
    with pytest.raises(ValueError, match="só pode resolver PENDING/UNKNOWN"):
        store.reconcile("req-1", ExecutionLifecycleState.REJECTED, updated_at=now)


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
