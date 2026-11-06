from __future__ import annotations

from core.runtime_process_lock import RuntimeProcessLock, RuntimeProcessLockSet


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


def test_runtime_lock_sets_block_different_runtimes_sharing_one_database(tmp_path):
    shared_database = tmp_path / "shared" / "fiscal.sqlite3"
    first = RuntimeProcessLockSet(
        tmp_path / "runtime-a" / "runtime.lock",
        [shared_database],
    )
    second = RuntimeProcessLockSet(
        tmp_path / "runtime-b" / "runtime.lock",
        [shared_database],
    )

    first.acquire()
    try:
        assert first.is_acquired is True
        assert second.is_acquired is False
        try:
            second.acquire()
        except RuntimeError as exc:
            assert "outra instância" in str(exc)
        else:
            raise AssertionError(
                "runtime diferente não pode ignorar o lock do banco compartilhado"
            )
        assert second.is_acquired is False
    finally:
        first.release()

    second.acquire()
    assert second.is_acquired is True
    second.release()
    assert second.is_acquired is False


def test_runtime_lock_set_rolls_back_partial_acquisition(tmp_path):
    shared_database = tmp_path / "shared" / "assistant.sqlite3"
    owner = RuntimeProcessLockSet(
        tmp_path / "runtime-owner" / "runtime.lock",
        [shared_database],
    )
    contender = RuntimeProcessLockSet(
        tmp_path / "runtime-contender" / "runtime.lock",
        [shared_database],
    )

    owner.acquire()
    try:
        try:
            contender.acquire()
        except RuntimeError:
            pass
        else:
            raise AssertionError("o lock compartilhado deveria bloquear o contender")
        assert contender.is_acquired is False
    finally:
        owner.release()

    # The contender's earlier partial lock (if acquired before the conflict)
    # must have been released, so a fresh lock set can now acquire every path.
    fresh = RuntimeProcessLockSet(
        tmp_path / "runtime-contender" / "runtime.lock",
        [shared_database],
    )
    fresh.acquire()
    assert fresh.is_acquired is True
    fresh.release()


def test_lock_set_preserves_acquisition_error_when_rollback_also_fails(tmp_path):
    lock_set = RuntimeProcessLockSet(tmp_path / "runtime.lock")
    released = []

    class _AcquiredLock:
        def acquire(self):
            return None

        def release(self):
            released.append("release")
            raise OSError("rollback release failed")

    class _FailingLock:
        def acquire(self):
            raise ValueError("original acquisition failure")

        def release(self):
            raise AssertionError("unacquired lock must not be released")

    lock_set._locks = [_AcquiredLock(), _FailingLock()]

    try:
        lock_set.acquire()
    except ValueError as exc:
        assert str(exc) == "original acquisition failure"
    else:
        raise AssertionError("the original acquisition error must be propagated")

    assert released == ["release"]
    assert lock_set.is_acquired is False
