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


class BrokerAdapterGateway:
    """Thin broker boundary; it never contains trading or signal logic."""

    def __init__(self, registry: BrokerRegistry) -> None:
        self._registry = registry

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
            # A transport/adapter exception is not a definitive rejection.
            # The request may have reached the broker before the exception, so
            # REAL execution must enter UNKNOWN rather than REJECTED.
            raise AdapterGatewayError(f"adapter falhou; execução não confirmada: {exc}") from exc

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.")

        return AdapterExecutionResult(result.accepted, result.message, result)
