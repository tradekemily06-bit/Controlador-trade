from __future__ import annotations

from core.runtime_process_lock import RuntimeProcessLock


def test_runtime_process_lock_creates_and_releases_lock_file(tmp_path):
    path = tmp_path / "runtime.lock"
    lock = RuntimeProcessLock(path)
    lock.acquire()
    assert path.exists()
    lock.release()
    lock.release()


def test_runtime_process_lock_rejects_reentrant_acquire_on_same_instance(tmp_path):
    lock = RuntimeProcessLock(tmp_path / "runtime.lock")
    lock.acquire()
    try:
        try:
            lock.acquire()
        except RuntimeError as exc:
            assert "já está adquirido" in str(exc)
        else:
            raise AssertionError("reentrada do mesmo lock deveria ser recusada")
    finally:
        lock.release()
