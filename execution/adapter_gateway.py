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

    def adapter_id(self, broker: str) -> str:
        """Return the adapter identity bound to a broker registration."""
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError as exc:
            raise AdapterGatewayError(str(exc)) from exc
        adapter_id = getattr(adapter, "adapter_id", None)
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise AdapterGatewayError("adapter REAL sem identidade explícita; dispatch bloqueado.")
        return adapter_id.strip()

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
            return AdapterExecutionResult(False, f"adapter falhou; execução não confirmada: {exc}")

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.")

        return AdapterExecutionResult(result.accepted, result.message, result)
