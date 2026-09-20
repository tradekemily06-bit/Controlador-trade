from datetime import datetime, timezone
from pathlib import Path

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
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now, "uncertain"))
    with pytest.raises(ValueError, match="UNKNOWN"):
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now, "accepted"))


def test_snapshot_is_lock_consistent(tmp_path: Path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    snapshot = store.snapshot()
    assert snapshot["req-1"].state is ExecutionLifecycleState.PENDING


def test_new_cycle_cannot_start_terminal_or_unknown(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)

    with pytest.raises(ValueError, match="transição inválida"):
        store.put(ExecutionLifecycleRecord("req-terminal", ExecutionLifecycleState.ACCEPTED, now))
    with pytest.raises(ValueError, match="transição inválida"):
        store.put(ExecutionLifecycleRecord("req-unknown", ExecutionLifecycleState.UNKNOWN, now))


def test_terminal_states_cannot_be_overwritten(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.REJECTED, now))
    with pytest.raises(ValueError, match="transição inválida"):
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now, "accepted"))


def test_unknown_requires_explicit_reconciliation(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
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


def test_records_read_is_lock_consistent(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-b", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-a", ExecutionLifecycleState.PENDING, now))
    assert [record.request_id for record in store.records()] == ["req-a", "req-b"]


def test_repair_from_durable_terminal_reconstructs_missing_lifecycle(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    result = store.repair_from_durable_terminal(
        "req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now, message="recovered"
    )
    assert result.state is ExecutionLifecycleState.ACCEPTED
    assert ExecutionLifecycleStore(path).get("req-1") == result


def test_repair_from_durable_terminal_refuses_conflicting_terminal(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.REJECTED, now))
    with pytest.raises(ValueError, match="terminal divergente"):
        store.repair_from_durable_terminal("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now, message="bad")
