from __future__ import annotations

import pytest

from integration.standalone_runtime import StandaloneRuntime


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

    def release(self) -> None:
        self.released = True


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
