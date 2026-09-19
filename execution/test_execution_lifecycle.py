from datetime import datetime, timezone

from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


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
