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
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "ponte MT5 remota aceita somente DEMO.")

        try:
            health = self._bridge.health()
        except Exception as exc:
            return ExecutionResult(False, f"ponte MT5 bloqueada: health falhou: {exc}")
        if not isinstance(health, BridgeHealth):
            return ExecutionResult(False, "ponte MT5 bloqueada: health inválido.")
        if type(health.available) is not bool or type(health.demo_account) is not bool:
            return ExecutionResult(False, "ponte MT5 bloqueada: flags de health inválidas.")
        if type(health.message) is not str or not health.message.strip():
            return ExecutionResult(False, "ponte MT5 bloqueada: mensagem de health inválida.")
        if not health.available or not health.demo_account:
            return ExecutionResult(False, f"ponte MT5 bloqueada: {health.message}")
        try:
            result = self._bridge.execute_demo(request)
        except Exception as exc:
            return ExecutionResult(False, f"ponte MT5 bloqueada: execução DEMO falhou: {exc}")
        if not isinstance(result, ExecutionResult):
            return ExecutionResult(False, "ponte MT5 retornou resultado inválido.")
        if type(result.accepted) is not bool:
            return ExecutionResult(False, "ponte MT5 retornou accepted inválido.")
        if type(result.message) is not str or not result.message.strip():
            return ExecutionResult(False, "ponte MT5 retornou message inválida.")
        if result.external_id is not None and (
            type(result.external_id) is not str or not result.external_id.strip()
        ):
            return ExecutionResult(False, "ponte MT5 retornou external_id inválido.")
        return result
