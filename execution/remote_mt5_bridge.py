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

    def lookup_demo(self, request_id: str): ...


class SafeRemoteMT5Executor:
    adapter_id = "remote-mt5-demo-v1"

    """Fail-closed execution facade for a remote MT5 bridge."""

    def __init__(self, bridge: RemoteMT5Bridge) -> None:
        self._bridge = bridge

    @staticmethod
    def correlation_for(request: ExecutionRequest) -> str:
        if not isinstance(request, ExecutionRequest) or not isinstance(request.request_id, str) or not request.request_id.strip():
            raise ValueError("request_id obrigatório para correlation bridge MT5")
        import hashlib
        return "CTD-BRIDGE-" + hashlib.sha256(request.request_id.strip().encode("utf-8")).hexdigest()[:24]

    def is_available(self) -> bool:
        try:
            health = self._bridge.health()
        except Exception:
            return False
        return self._valid_demo_health(health)

    @staticmethod
    def _valid_demo_health(health: BridgeHealth) -> bool:
        """Validate the bridge health contract before trusting environment state."""
        return (
            type(health) is BridgeHealth
            and health.available is True
            and health.demo_account is True
            and isinstance(health.message, str)
            and bool(health.message.strip())
        )

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return ExecutionResult(False, "request de execução inválido.")
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "ponte MT5 remota aceita somente DEMO.")
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            return ExecutionResult(False, "request_id obrigatório para execução DEMO.")

        try:
            health = self._bridge.health()
        except Exception as exc:
            return ExecutionResult(False, f"ponte MT5 bloqueada: falha de health check: {exc}")
        if not self._valid_demo_health(health):
            return ExecutionResult(False, f"ponte MT5 bloqueada: {health.message}")

        try:
            result = self._bridge.execute_demo(request)
        except Exception as exc:
            return ExecutionResult(
                False,
                f"ponte MT5 falhou após despacho potencial; resultado incerto: {type(exc).__name__}: {exc}",
                uncertain=True,
            )
        if not isinstance(result, ExecutionResult):
            return ExecutionResult(False, "ponte MT5 retornou resultado inválido; estado externo incerto.", uncertain=True)
        if result.accepted and (not isinstance(result.external_id, str) or not result.external_id.strip()):
            return ExecutionResult(False, "ponte MT5 aceitou sem external_id; estado externo incerto.", uncertain=True)
        return result
