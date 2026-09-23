from __future__ import annotations

import threading
import time

from integration.persistent_broker_connection import PersistentBrokerConnectionRuntime


class BlockingAdapter:
    def __init__(self) -> None:
        self.connect_started = threading.Event()
        self.allow_connect = threading.Event()
        self.disconnect_started = threading.Event()
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.available = False

    def connect(self) -> bool:
        self.connect_calls += 1
        self.connect_started.set()
        self.allow_connect.wait(timeout=2)
        self.available = True
        return True

    def disconnect(self) -> None:
        self.disconnect_started.set()
        self.available = False
        self.disconnect_calls += 1

    def is_available(self) -> bool:
        return self.available


def test_user_disconnect_serializes_against_connect_and_stale_start_disconnects() -> None:
    adapter = BlockingAdapter()
    runtime = PersistentBrokerConnectionRuntime(adapter, poll_seconds=60)

    start_thread = threading.Thread(target=runtime.start)
    start_thread.start()
    assert adapter.connect_started.wait(timeout=1)

    disconnect_thread = threading.Thread(target=runtime.user_disconnect)
    disconnect_thread.start()
    time.sleep(0.05)

    # Disconnect must not run concurrently with an in-flight connect.
    assert adapter.disconnect_calls == 0
    assert disconnect_thread.is_alive()

    adapter.allow_connect.set()
    start_thread.join(timeout=2)
    disconnect_thread.join(timeout=2)

    assert not start_thread.is_alive()
    assert not disconnect_thread.is_alive()
    assert adapter.connect_calls == 1
    assert adapter.disconnect_calls == 1
    status = runtime.status()
    assert status.user_disconnected is True
    assert status.adapter_available is False


def test_repeated_start_does_not_create_multiple_connection_threads() -> None:
    class Adapter:
        def __init__(self) -> None:
            self.connect_calls = 0
            self.available = True

        def connect(self) -> bool:
            self.connect_calls += 1
            return True

        def disconnect(self) -> None:
            self.available = False

        def is_available(self) -> bool:
            return self.available

    adapter = Adapter()
    runtime = PersistentBrokerConnectionRuntime(adapter, poll_seconds=60)

    runtime.start()
    runtime.start()

    assert adapter.connect_calls == 1
    runtime.user_disconnect()
