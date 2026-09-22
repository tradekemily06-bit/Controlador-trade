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
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            return ExecutionResult(False, "request_id obrigatório para ponte MT5 DEMO.")
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "ponte MT5 remota aceita somente DEMO.")

        try:
            health = self._bridge.health()
        except Exception as exc:
            return ExecutionResult(False, f"ponte MT5 bloqueada: health check falhou: {type(exc).__name__}: {exc}")
        if type(health) is not BridgeHealth or health.available is not True or health.demo_account is not True or not isinstance(health.message, str) or not health.message.strip():
            return ExecutionResult(False, "ponte MT5 bloqueada: health check inválido ou conta DEMO não confirmada.")

        try:
            result = self._bridge.execute_demo(request)
        except Exception as exc:
            return ExecutionResult(False, f"ponte MT5 falhou após despacho potencial; resultado incerto: {type(exc).__name__}: {exc}", ambiguous=True)
        if not isinstance(result, ExecutionResult):
            return ExecutionResult(False, "ponte MT5 retornou resultado inválido; estado externo incerto.", ambiguous=True)
        if result.accepted and (not isinstance(result.external_id, str) or not result.external_id.strip()):
            return ExecutionResult(False, "ponte MT5 aceitou sem external_id; estado externo incerto.", ambiguous=True)
        return result
