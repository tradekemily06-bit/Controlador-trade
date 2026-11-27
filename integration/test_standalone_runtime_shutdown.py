from __future__ import annotations

import threading

import pytest

from integration.standalone_runtime import (
    StandaloneRuntime,
    _FAILED_STARTUP_LOCKS,
    _cleanup_failed_startup,
)


class FakeWorker:
    def __init__(self, running_key: str) -> None:
        self.running_key = running_key
        self.running = True
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1

    def status(self) -> dict[str, bool]:
        return {self.running_key: self.running}


class FakeLock:
    def __init__(self) -> None:
        self.released = False
        self.released_event = threading.Event()

    def release(self) -> None:
        self.released = True
        self.released_event.set()


@pytest.mark.parametrize(
    ("attribute", "running_key"),
    (
        ("market_monitor", "worker_running"),
        ("notification_worker", "running"),
        ("backup_scheduler", "worker_running"),
    ),
)
def test_runtime_keeps_process_lock_until_each_worker_has_stopped(
    attribute: str, running_key: str
) -> None:
    runtime = StandaloneRuntime.__new__(StandaloneRuntime)
    runtime.closed = False
    runtime.process_lock = FakeLock()
    runtime.market_monitor = None
    runtime.notification_worker = None
    runtime.backup_scheduler = None
    worker = FakeWorker(running_key)
    setattr(runtime, attribute, worker)

    with pytest.raises(RuntimeError, match="workers ativos"):
        runtime.close()

    assert worker.stop_calls == 1
    assert runtime.process_lock.released is False
    assert runtime.closed is False

    worker.running = False
    runtime.close()

    assert worker.stop_calls == 2
    assert runtime.process_lock.released is True
    assert runtime.closed is True


def test_runtime_close_is_idempotent_after_successful_shutdown() -> None:
    runtime = StandaloneRuntime.__new__(StandaloneRuntime)
    runtime.closed = False
    runtime.process_lock = FakeLock()
    runtime.market_monitor = None
    runtime.notification_worker = None
    runtime.backup_scheduler = None

    runtime.close()
    runtime.close()

    assert runtime.process_lock.released is True
    assert runtime.closed is True



def test_failed_startup_retains_process_lock_when_worker_is_still_running() -> None:
    lock = FakeLock()
    worker = FakeWorker("worker_running")
    before = len(_FAILED_STARTUP_LOCKS)

    active = _cleanup_failed_startup(lock, ((worker, "worker_running"),))

    assert active == ["FakeWorker"]
    assert worker.stop_calls == 1
    assert lock.released is False
    assert len(_FAILED_STARTUP_LOCKS) == before + 1
    retained_lock, retained_workers = _FAILED_STARTUP_LOCKS[-1]
    assert retained_lock is lock
    assert retained_workers == ((worker, "worker_running"),)


def test_failed_startup_releases_lock_when_all_workers_stopped() -> None:
    lock = FakeLock()
    worker = FakeWorker("worker_running")
    worker.running = False

    active = _cleanup_failed_startup(lock, ((worker, "worker_running"),))

    assert active == []
    assert worker.stop_calls == 1
    assert lock.released is True


def test_failed_startup_retains_lock_when_worker_status_cannot_be_read() -> None:
    class BrokenStatusWorker(FakeWorker):
        def status(self) -> dict[str, bool]:
            raise RuntimeError("status unavailable")

    lock = FakeLock()
    worker = BrokenStatusWorker("worker_running")
    before = len(_FAILED_STARTUP_LOCKS)

    active = _cleanup_failed_startup(lock, ((worker, "worker_running"),))

    assert active == ["BrokenStatusWorker"]
    assert lock.released is False
    assert len(_FAILED_STARTUP_LOCKS) == before + 1



def test_failed_startup_reaper_releases_lock_after_worker_exits() -> None:
    lock = FakeLock()
    worker = FakeWorker("worker_running")

    active = _cleanup_failed_startup(lock, ((worker, "worker_running"),))
    assert active == ["FakeWorker"]
    assert lock.released is False

    worker.running = False
    assert lock.released_event.wait(timeout=2.0)
    assert lock.released is True
    assert all(item[0] is not lock for item in _FAILED_STARTUP_LOCKS)



def test_runtime_keeps_lock_when_worker_status_does_not_confirm_stopped() -> None:
    class UnknownStatusWorker(FakeWorker):
        def status(self) -> dict[str, bool]:
            return {} if self.running else {self.running_key: False}

    runtime = StandaloneRuntime.__new__(StandaloneRuntime)
    runtime.closed = False
    runtime.process_lock = FakeLock()
    runtime.market_monitor = None
    runtime.notification_worker = None
    runtime.backup_scheduler = None
    worker = UnknownStatusWorker("worker_running")
    runtime.market_monitor = worker

    with pytest.raises(RuntimeError, match="workers ativos"):
        runtime.close()

    assert runtime.process_lock.released is False
    assert runtime.closed is False

    worker.running = False
    runtime.close()

    assert runtime.process_lock.released is True
    assert runtime.closed is True



def test_failed_startup_reaper_waits_for_explicit_stopped_status() -> None:
    class UnknownStatusWorker(FakeWorker):
        def status(self) -> dict[str, bool]:
            return {} if self.running else {self.running_key: False}

    lock = FakeLock()
    worker = UnknownStatusWorker("worker_running")

    active = _cleanup_failed_startup(lock, ((worker, "worker_running"),))
    assert active == ["UnknownStatusWorker"]
    assert lock.released is False
    assert not lock.released_event.wait(timeout=0.1)

    worker.running = False
    assert lock.released_event.wait(timeout=2.0)
    assert lock.released is True
    assert all(item[0] is not lock for item in _FAILED_STARTUP_LOCKS)
