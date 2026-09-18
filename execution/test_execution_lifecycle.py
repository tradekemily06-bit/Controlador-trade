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


def test_naive_timestamp_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="timezone-aware"):
        ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, datetime(2026, 1, 1))


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


def test_put_does_not_mutate_memory_when_persistence_fails(tmp_path, monkeypatch):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    original = ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now, "started")
    store.put(original)

    def fail_save(_records):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_save", fail_save)
    replacement = ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now, "accepted")
    with pytest.raises(OSError, match="disk full"):
        store.put(replacement)

    assert store.get("req-1") == original
    assert ExecutionLifecycleStore(path).get("req-1") == original


def test_reload_reflects_external_removal_without_stale_memory(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    path.unlink()

    assert store.get("req-1") is None
    assert store.records() == ()


def test_terminal_states_cannot_regress_to_pending(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    for terminal in (ExecutionLifecycleState.ACCEPTED, ExecutionLifecycleState.REJECTED, ExecutionLifecycleState.UNKNOWN):
        request_id = f"{terminal.value.lower()}-req"
        store.put(ExecutionLifecycleRecord(request_id, terminal, now))
        with pytest.raises(ValueError):
            store.put(ExecutionLifecycleRecord(request_id, ExecutionLifecycleState.PENDING, now, "regression"))


def test_reconciliation_cannot_override_non_unknown_state(tmp_path):
    path = tmp_path / "lifecycle.json"
    now = datetime.now(timezone.utc)
    store = ExecutionLifecycleStore(path)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))
    with pytest.raises(ValueError, match="UNKNOWN"):
        store.reconcile("req-1", ExecutionLifecycleState.REJECTED, updated_at=now)
