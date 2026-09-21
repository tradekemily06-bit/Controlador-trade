import pytest

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


def test_lifecycle_persistence_flushes_before_atomic_replace(tmp_path, monkeypatch):
    import os
    path = tmp_path / "lifecycle.json"
    store = ExecutionLifecycleStore(path)
    calls = []
    real_fsync = os.fsync
    real_replace = os.replace

    def fsync(fd):
        calls.append("fsync")
        return real_fsync(fd)

    def replace(src, dst):
        calls.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    store.put(ExecutionLifecycleRecord("req-durable", ExecutionLifecycleState.PENDING, datetime.now(timezone.utc)))
    assert calls.index("fsync") < calls.index("replace")
    assert calls.count("fsync") >= (1 if os.name == "nt" else 2)


def test_persisted_lifecycle_rejects_duplicate_request_id(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text(
        '[{"request_id":"dup","state":"PENDING","updated_at":"2026-01-01T00:00:00+00:00"},'
        '{"request_id":"dup","state":"UNKNOWN","updated_at":"2026-01-01T00:00:01+00:00"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="request_id duplicado"):
        ExecutionLifecycleStore(path)


def test_persisted_lifecycle_rejects_timezone_naive_timestamp(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text(
        '[{"request_id":"naive","state":"PENDING","updated_at":"2026-01-01T00:00:00"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        ExecutionLifecycleStore(path)


def test_windows_lock_initializes_lock_byte(tmp_path, monkeypatch):
    import execution.execution_lifecycle as lifecycle_module

    class FakeMSVCRT:
        LK_LOCK = 1
        LK_UNLCK = 2

        def __init__(self):
            self.calls = []

        def locking(self, fd, mode, size):
            self.calls.append((fd, mode, size))

    fake_msvcrt = FakeMSVCRT()
    monkeypatch.setattr(lifecycle_module, "fcntl", None)
    monkeypatch.setattr(lifecycle_module, "msvcrt", fake_msvcrt)

    store = lifecycle_module.ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(lifecycle_module.ExecutionLifecycleRecord("windows-lock", lifecycle_module.ExecutionLifecycleState.PENDING, now))

    lock_path = tmp_path / ".lifecycle.json.lock"
    assert lock_path.read_bytes() == b"0"
    assert any(mode == fake_msvcrt.LK_LOCK and size == 1 for _, mode, size in fake_msvcrt.calls)
