from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from execution.ports import ExecutionRequest, ExecutionResult


class RemoteBridgeError(RuntimeError):
    """Raised when the remote MT5 bridge cannot safely be used."""


@dataclass(frozen=True)
class BridgeHealth:
    available: bool
    demo_account: bool
    message: str


class RemoteMT5Bridge(Protocol):
    """Transport boundary for a cloud-hosted MT5 terminal.

    The Controlador Trading process never receives broker credentials here.
    A separate bridge process owns the local MetaTrader 5 terminal and exposes
    only authenticated, DEMO-scoped operations to the ecosystem.
    """

    def health(self) -> BridgeHealth: ...

    def execute_demo(self, request: ExecutionRequest) -> ExecutionResult: ...


class SafeRemoteMT5Executor:
    """Fail-closed execution facade for a remote MT5 bridge."""

    def __init__(self, bridge: RemoteMT5Bridge) -> None:
        self._bridge = bridge

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        # REAL is intentionally impossible through this boundary.
        if request.mode.value != "DEMO":
            return ExecutionResult(False, "ponte MT5 remota aceita somente DEMO.")

        health = self._bridge.health()
        if not health.available or not health.demo_account:
            return ExecutionResult(False, f"ponte MT5 bloqueada: {health.message}")

        return self._bridge.execute_demo(request)
