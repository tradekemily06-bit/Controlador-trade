from __future__ import annotations

from dataclasses import dataclass

from execution.broker_registry import (
    BrokerRegistry,
    BrokerRegistryError,
    _BROKER_GATEWAY_CAPABILITY,
)
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class AdapterGatewayError(RuntimeError):
    """Raised when an adapter cannot safely receive an execution request."""


@dataclass(frozen=True)
class AdapterExecutionResult:
    accepted: bool
    message: str
    execution: ExecutionResult | None = None
    # True means the adapter was invoked but its terminal outcome was not
    # safely established. REAL must preserve this as UNKNOWN.
    uncertain: bool = False
    # Exact immutable adapter identity resolved by the registry for this call.
    adapter_id: str | None = None


class BrokerAdapterGateway:
    """Single broker execution boundary; adapters never leave the registry."""

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        """Expose only the exception type across the broker boundary."""
        return type(exc).__name__

    def __init__(self, registry: BrokerRegistry) -> None:
        if not isinstance(registry, BrokerRegistry):
            raise ValueError("registry inválido.")
        self._registry = registry

    def adapter_id(self, broker: str) -> str:
        """Resolve adapter identity without exposing the executable adapter."""
        try:
            return self._registry.adapter_id(broker)
        except BrokerRegistryError as exc:
            raise AdapterGatewayError(f"adapter identity unavailable: {self._safe_error(exc)}") from exc

    def execute(self, broker: str, request: ExecutionRequest) -> AdapterExecutionResult:
        # This boundary is reserved for the explicit REAL dispatch path.
        # DEMO must stay behind the DEMO gateway/executor so a low-level broker
        # adapter cannot accidentally become an execution bypass.
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.REAL:
            return AdapterExecutionResult(False, "broker adapter rejeitou requisição fora do modo REAL.")

        try:
            adapter = self._registry._get_for_gateway(
                broker,
                capability=_BROKER_GATEWAY_CAPABILITY,
            )
            resolved_adapter_id = self._registry.adapter_id(broker)
        except BrokerRegistryError as exc:
            return AdapterExecutionResult(False, f"broker registry rejected request: {self._safe_error(exc)}")

        try:
            available = adapter.is_available()
        except Exception as exc:
            return AdapterExecutionResult(False, f"adapter availability check failed: {self._safe_error(exc)}", adapter_id=resolved_adapter_id)

        if not isinstance(available, bool):
            return AdapterExecutionResult(False, "adapter availability returned an invalid non-boolean state.", adapter_id=resolved_adapter_id)
        if not available:
            return AdapterExecutionResult(False, "adapter indisponível; execução não encaminhada.", adapter_id=resolved_adapter_id)

        try:
            result = adapter.execute(request)
        except Exception as exc:
            return AdapterExecutionResult(
                False,
                f"adapter execution failed; execution not confirmed: {self._safe_error(exc)}",
                uncertain=True,
                adapter_id=resolved_adapter_id,
            )

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(
                False,
                "adapter retornou resultado inválido; execução não confirmável.",
                uncertain=True,
                adapter_id=resolved_adapter_id,
            )
        if not isinstance(result.accepted, bool):
            return AdapterExecutionResult(
                False,
                "adapter retornou estado de aceite inválido; execução não confirmável.",
                uncertain=True,
                adapter_id=resolved_adapter_id,
            )
        if not isinstance(result.message, str):
            return AdapterExecutionResult(
                False,
                "adapter retornou mensagem inválida; execução não confirmável.",
                uncertain=True,
                adapter_id=resolved_adapter_id,
            )

        return AdapterExecutionResult(result.accepted, result.message, result, adapter_id=resolved_adapter_id)
