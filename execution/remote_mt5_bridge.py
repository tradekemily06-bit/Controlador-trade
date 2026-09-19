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
    """Fail-closed execution facade for a remote MT5 bridge."""

    def __init__(self, bridge: RemoteMT5Bridge) -> None:
        self._bridge = bridge

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return ExecutionResult(False, "requisição de execução inválida.")
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "ponte MT5 remota aceita somente DEMO.")

        try:
            health = self._bridge.health()
        except Exception as exc:
            return ExecutionResult(False, f"health da ponte MT5 falhou: {type(exc).__name__}")
        if not isinstance(health, BridgeHealth):
            return ExecutionResult(False, "health da ponte MT5 retornou resultado inválido.")
        if not health.available or not health.demo_account:
            return ExecutionResult(False, "ponte MT5 bloqueada; health remoto não autoriza execução.")

        try:
            result = self._bridge.execute_demo(request)
        except Exception as exc:
            return ExecutionResult(False, f"execução remota MT5 não confirmada: {type(exc).__name__}")
        if not isinstance(result, ExecutionResult):
            return ExecutionResult(False, "ponte MT5 retornou resultado de execução inválido.")
        return result
