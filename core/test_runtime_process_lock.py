from __future__ import annotations

from core.runtime_process_lock import RuntimeProcessLock


def test_runtime_process_lock_creates_and_releases_lock_file(tmp_path):
    path = tmp_path / "runtime.lock"
    lock = RuntimeProcessLock(path)
    lock.acquire()
    assert path.exists()
    assert lock.is_acquired is True
    lock.release()
    assert lock.is_acquired is False
    lock.release()


def test_runtime_process_lock_rejects_reentrant_acquire_on_same_instance(tmp_path):
    lock = RuntimeProcessLock(tmp_path / "runtime.lock")
    lock.acquire()
    assert lock.is_acquired is True
    try:
        try:
            lock.acquire()
        except RuntimeError as exc:
            assert "já está adquirido" in str(exc)
        else:
            raise AssertionError("reentrada do mesmo lock deveria ser recusada")
    finally:
        lock.release()
    assert lock.is_acquired is False


def test_runtime_process_lock_serializes_distinct_instances_for_same_path(tmp_path):
    path = tmp_path / "runtime.lock"
    first = RuntimeProcessLock(path)
    second = RuntimeProcessLock(path)

    first.acquire()
    try:
        assert first.is_acquired is True
        assert second.is_acquired is False
        try:
            second.acquire()
        except RuntimeError as exc:
            assert "outra instância" in str(exc)
        else:
            raise AssertionError("uma segunda instância deveria ser bloqueada")

        # A failed acquisition must not leave the second object holding a
        # descriptor that could be mistaken for ownership.
        assert second.is_acquired is False
    finally:
        first.release()

    # The same second instance must remain usable after the owner releases.
    second.acquire()
    assert second.is_acquired is True
    second.release()
    assert second.is_acquired is False
