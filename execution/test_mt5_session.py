from __future__ import annotations

from types import SimpleNamespace

import pytest

from execution.mt5_session import MT5SessionConflict, MT5SessionCoordinator


class FakeMT5:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.shutdown_calls = 0

    def initialize(self) -> bool:
        self.initialize_calls += 1
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def test_same_mode_shares_session_and_shutdowns_only_after_last_owner() -> None:
    mt5 = FakeMT5()
    coordinator = MT5SessionCoordinator()

    assert coordinator.acquire(mt5, mode="DEMO", owner="market") is True
    assert coordinator.acquire(mt5, mode="DEMO", owner="execution") is True
    assert mt5.initialize_calls == 1
    assert coordinator.status()["owners"] == 2

    coordinator.release(mt5, owner="market")
    assert mt5.shutdown_calls == 0
    assert coordinator.status()["owners"] == 1

    coordinator.release(mt5, owner="execution")
    assert mt5.shutdown_calls == 1
    assert coordinator.status()["state"] == "DISCONNECTED"


def test_demo_real_conflict_is_fail_closed() -> None:
    mt5 = FakeMT5()
    coordinator = MT5SessionCoordinator()

    assert coordinator.acquire(mt5, mode="DEMO", owner="demo") is True
    assert coordinator.acquire(mt5, mode="REAL", owner="real") is False
    assert mt5.initialize_calls == 1
    assert coordinator.status()["mode"] == "DEMO"


def test_operation_requires_active_owner_and_matching_mode() -> None:
    mt5 = FakeMT5()
    coordinator = MT5SessionCoordinator()

    assert coordinator.acquire(mt5, mode="REAL", owner="real") is True

    with coordinator.operation(mt5, mode="REAL", owner="real"):
        pass

    with pytest.raises(MT5SessionConflict):
        with coordinator.operation(mt5, mode="DEMO", owner="real"):
            pass

    with pytest.raises(MT5SessionConflict):
        with coordinator.operation(mt5, mode="REAL", owner="other"):
            pass


def test_different_module_cannot_hijack_active_session() -> None:
    first = FakeMT5()
    second = FakeMT5()
    coordinator = MT5SessionCoordinator()

    assert coordinator.acquire(first, mode="DEMO", owner="first") is True

    with pytest.raises(MT5SessionConflict):
        coordinator.acquire(second, mode="DEMO", owner="second")

    assert second.initialize_calls == 0
    assert first.shutdown_calls == 0
