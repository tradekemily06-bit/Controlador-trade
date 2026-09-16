from __future__ import annotations

from dataclasses import dataclass

from execution.broker_registry import BrokerRegistry, BrokerRegistryError
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class AdapterGatewayError(RuntimeError):
    """Raised when an adapter cannot safely receive or confirm an execution request."""


@dataclass(frozen=True)
class AdapterExecutionResult:
    accepted: bool
    message: str
    execution: ExecutionResult | None = None


class BrokerAdapterGateway:
    """Thin REAL broker boundary; operational authorization stays upstream."""

    def __init__(self, registry: BrokerRegistry) -> None:
        self._registry = registry

    def execute(self, broker: str, request: ExecutionRequest) -> AdapterExecutionResult:
        # DEMO/PAPER execution must never reach a broker adapter directly.
        if not isinstance(request, ExecutionRequest):
            return AdapterExecutionResult(False, "request de execução inválido.")
        if request.mode is not ExecutionMode.REAL:
            return AdapterExecutionResult(False, "broker adapter aceita somente REAL; DEMO deve passar pelo gateway operacional.")

        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError as exc:
            return AdapterExecutionResult(False, str(exc))

        try:
            available = bool(adapter.is_available())
        except Exception as exc:
            return AdapterExecutionResult(False, f"disponibilidade do adapter falhou: {type(exc).__name__}")

        if not available:
            return AdapterExecutionResult(False, "adapter indisponível; execução não encaminhada.")

        try:
            result = adapter.execute(request)
        except Exception as exc:
            # The broker may have accepted the order before the client observed
            # the exception. Preserve UNKNOWN so the REAL gateway can reconcile.
            raise AdapterGatewayError("adapter execution outcome is unknown") from exc

        if not isinstance(result, ExecutionResult):
            raise AdapterGatewayError("adapter retornou resultado inválido; resultado REAL é UNKNOWN")

        return AdapterExecutionResult(result.accepted, result.message, result)
