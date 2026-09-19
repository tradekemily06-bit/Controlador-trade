from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


@dataclass(frozen=True)
class BridgeHealth:
    available: bool
    demo_account: bool
    message: str


class RemoteMT5Bridge(Protocol):
    """Transport boundary for a cloud-hosted MT5 terminal."""

    def health(self) -> BridgeHealth: ...

    def execute_demo(self, request: ExecutionRequest) -> ExecutionResult: ...


class SafeRemoteMT5Executor:
    adapter_id = "remote-mt5-demo-v1"

    """Fail-closed execution facade for a remote MT5 bridge."""

    def __init__(self, bridge: RemoteMT5Bridge) -> None:
        self._bridge = bridge

    def is_available(self) -> bool:
        try:
            health = self._bridge.health()
        except Exception:
            return False
        return bool(health.available and health.demo_account)

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return ExecutionResult(False, "request de execução inválido.")
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "ponte MT5 remota aceita somente DEMO.")

        try:
            health = self._bridge.health()
        except Exception as exc:
            return ExecutionResult(False, f"ponte MT5 bloqueada: falha de health check: {exc}")
        if not health.available or not health.demo_account:
            return ExecutionResult(False, f"ponte MT5 bloqueada: {health.message}")

        return self._bridge.execute_demo(request)
