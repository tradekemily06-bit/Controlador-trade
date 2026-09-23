from datetime import datetime, timezone

from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)


def test_lifecycle_store_preserves_updates_from_multiple_instances(tmp_path):
    path = tmp_path / "lifecycle.json"
    first = ExecutionLifecycleStore(path)
    second = ExecutionLifecycleStore(path)
    now = datetime.now(timezone.utc)

    first.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now, "one"))
    second.put(ExecutionLifecycleRecord("req-2", ExecutionLifecycleState.PENDING, now, "two"))

    reloaded = ExecutionLifecycleStore(path)
    assert {item.request_id for item in reloaded.records()} == {"req-1", "req-2"}


def test_unknown_lifecycle_requires_explicit_reconciliation(tmp_path):
    path = tmp_path / "lifecycle.json"
    store = ExecutionLifecycleStore(path)
    now = datetime.now(timezone.utc)

    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.UNKNOWN, now, "uncertain"))

    try:
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.ACCEPTED, now, "replay"))
    except ValueError as exc:
        assert "UNKNOWN" in str(exc)
    else:
        raise AssertionError("UNKNOWN must not be overwritten without reconciliation")

    store.reconcile("req-1", ExecutionLifecycleState.ACCEPTED, updated_at=now, message="reconciled")
    assert store.get("req-1").state is ExecutionLifecycleState.ACCEPTED
