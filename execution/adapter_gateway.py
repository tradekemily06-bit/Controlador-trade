from __future__ import annotations

from dataclasses import dataclass

from execution.broker_registry import BrokerRegistry, BrokerRegistryError
from execution.ports import ExecutionRequest, ExecutionResult


class AdapterGatewayError(RuntimeError):
    """Raised when an adapter cannot safely receive an execution request."""


@dataclass(frozen=True)
class AdapterExecutionResult:
    accepted: bool
    message: str
    execution: ExecutionResult | None = None
    # True once adapter.execute() has actually been entered. An exception after
    # that point is potentially post-dispatch and must not be treated as a
    # definitive pre-dispatch rejection.
    dispatch_started: bool = False


class BrokerAdapterGateway:
    """Thin broker boundary; it never contains trading or signal logic."""

    def __init__(self, registry: BrokerRegistry) -> None:
        self._registry = registry

    def adapter_id(self, broker: str) -> str:
        return self._registry.adapter_id(broker)

    def execute(self, broker: str, request: ExecutionRequest) -> AdapterExecutionResult:
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError as exc:
            return AdapterExecutionResult(False, str(exc))

        try:
            available = bool(adapter.is_available())
        except Exception as exc:
            return AdapterExecutionResult(False, f"disponibilidade do adapter falhou: {exc}")

        if not available:
            return AdapterExecutionResult(False, "adapter indisponível; execução não encaminhada.")

        try:
            result = adapter.execute(request)
        except Exception as exc:
            return AdapterExecutionResult(False, f"adapter falhou; execução não confirmada: {exc}", dispatch_started=True)

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.", dispatch_started=True)

        return AdapterExecutionResult(result.accepted, result.message, result, dispatch_started=True)
