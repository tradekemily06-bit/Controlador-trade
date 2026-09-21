from __future__ import annotations

from dataclasses import dataclass

from execution.broker_registry import BrokerRegistry, BrokerRegistryError, _BROKER_ACCESS_CAPABILITY
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class AdapterGatewayError(RuntimeError):
    """Raised when an adapter cannot safely receive an execution request."""


# Private capability used only by RealExecutionGateway to cross the REAL adapter
# boundary. The public DEMO/generic gateway must never forward a REAL request.
_REAL_DISPATCH_CAPABILITY = object()


@dataclass(frozen=True)
class AdapterExecutionResult:
    accepted: bool
    message: str
    execution: ExecutionResult | None = None
    uncertain: bool = False


class BrokerAdapterGateway:
    """Broker boundary with an explicit split between generic/DEMO and REAL dispatch."""

    def __init__(self, registry: BrokerRegistry) -> None:
        self._registry = registry

    def adapter_id(self, broker: str) -> str | None:
        try:
            return self._registry.adapter_id(broker)
        except BrokerRegistryError:
            return None

    def execute(self, broker: str, request: ExecutionRequest) -> AdapterExecutionResult:
        """Generic/DEMO dispatch. REAL is rejected at this boundary."""
        if not isinstance(request, ExecutionRequest):
            return AdapterExecutionResult(False, "request de execução inválido.")
        if request.mode is ExecutionMode.REAL:
            return AdapterExecutionResult(
                False,
                "execução REAL exige a fronteira RealExecutionGateway.",
            )
        return self._dispatch(broker, request, preserve_exceptions=False)

    def execute_real(
        self,
        broker: str,
        request: ExecutionRequest,
        *,
        capability: object,
    ) -> AdapterExecutionResult:
        """REAL-only dispatch; callable only with the private gateway capability."""
        if capability is not _REAL_DISPATCH_CAPABILITY:
            return AdapterExecutionResult(False, "capacidade de despacho REAL inválida.")
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.REAL:
            return AdapterExecutionResult(False, "request REAL obrigatório na fronteira de despacho REAL.")
        return self._dispatch(broker, request, preserve_exceptions=True)

    def _dispatch(self, broker: str, request: ExecutionRequest, *, preserve_exceptions: bool) -> AdapterExecutionResult:
        try:
            adapter = self._registry.get(broker, capability=_BROKER_ACCESS_CAPABILITY)
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
            if preserve_exceptions:
                raise AdapterGatewayError(f"adapter REAL falhou após o despacho: {exc}") from exc
            return AdapterExecutionResult(False, f"adapter falhou; execução não confirmada: {exc}", ExecutionResult(False, f"adapter falhou; resultado externo incerto: {exc}", uncertain=True), True)

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.")

        return AdapterExecutionResult(result.accepted, result.message, result, result.uncertain)
