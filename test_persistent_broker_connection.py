from __future__ import annotations

import time

from integration.persistent_broker_connection import PersistentBrokerConnectionRuntime


class Adapter:
    def __init__(self, available=True):
        self.available = available
        self.calls = 0

    def is_available(self):
        self.calls += 1
        return self.available

    def execute(self, request):
        raise AssertionError("connection runtime must never execute orders")


def wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_connection_runtime_reconnects_without_execution_authority():
    adapter = Adapter()
    runtime = PersistentBrokerConnectionRuntime(adapter, poll_seconds=0.01)
    runtime.start()

    assert wait_until(lambda: runtime.status().adapter_available)
    assert runtime.status().state == "CONNECTED"
    assert adapter.calls > 0


def test_user_disconnect_blocks_automatic_reconnect():
    adapter = Adapter()
    runtime = PersistentBrokerConnectionRuntime(adapter, poll_seconds=0.01)
    runtime.start()
    assert wait_until(lambda: adapter.calls > 0)

    runtime.user_disconnect()
    calls = adapter.calls
    time.sleep(0.05)

    status = runtime.status()
    assert status.state == "USER_DISCONNECTED"
    assert status.user_disconnected is True
    assert status.adapter_available is False
    assert adapter.calls == calls
