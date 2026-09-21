from datetime import datetime, timezone

from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore, LIFECYCLE_RECOVERY_CAPABILITY


def test_lifecycle_store_reloads_before_mutation(tmp_path):
    path = tmp_path / "lifecycle.json"
    first = ExecutionLifecycleStore(path)
    second = ExecutionLifecycleStore(path)
    now = datetime.now(timezone.utc)
    first.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    second.put(ExecutionLifecycleRecord("req-2", ExecutionLifecycleState.PENDING, now))
    assert {r.request_id for r in ExecutionLifecycleStore(path).records()} == {"req-1", "req-2"}


def test_unknown_cannot_be_overwritten_without_reconciliation(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now))
    try:
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))
    except ValueError:
        pass
    else:
        raise AssertionError("UNKNOWN must require explicit reconciliation")


def test_reconcile_requires_unknown_state(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    try:
        store.reconcile("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now)
    except ValueError:
        pass
    else:
        raise AssertionError("reconciliation must not bypass UNKNOWN")


def test_lifecycle_rejects_non_pending_initial_state(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    try:
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))
    except ValueError:
        pass
    else:
        raise AssertionError("lifecycle must start in PENDING")


def test_lifecycle_terminal_state_is_immutable(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now))
    try:
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.REJECTED, now))
    except ValueError:
        pass
    else:
        raise AssertionError("terminal lifecycle state must be immutable")


def test_reconcile_missing_requires_internal_recovery_capability(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    try:
        store.reconcile_missing("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now)
    except ValueError:
        pass
    else:
        raise AssertionError("ledger-only lifecycle recovery must require an internal capability")
    store.reconcile_missing("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now, capability=LIFECYCLE_RECOVERY_CAPABILITY)
    assert store.get("req-1").state is ExecutionLifecycleState.ACCEPTED
