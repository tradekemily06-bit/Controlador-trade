from __future__ import annotations

from dataclasses import dataclass

from execution.broker_registry import BrokerRegistry, BrokerRegistryError
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


_REAL_DISPATCH_CAPABILITY = object()


class AdapterGatewayError(RuntimeError):
    """Raised when an adapter cannot safely receive an execution request."""


@dataclass(frozen=True)
class AdapterExecutionResult:
    accepted: bool
    message: str
    execution: ExecutionResult | None = None
    dispatch_attempted: bool = False


class BrokerAdapterGateway:
    """Thin broker boundary; it never contains trading or signal logic."""

    def __init__(self, registry: BrokerRegistry) -> None:
        self._registry = registry

    def execute(self, broker: str, request: ExecutionRequest) -> AdapterExecutionResult:
        """Public adapter path is DEMO-only; REAL requires the dedicated gateway."""
        if request.mode is ExecutionMode.REAL:
            return AdapterExecutionResult(
                False,
                "execução REAL deve passar exclusivamente pelo RealExecutionGateway.",
                dispatch_attempted=False,
            )
        return self._execute(broker, request)

    def execute_real(
        self,
        broker: str,
        request: ExecutionRequest,
        *,
        capability: object,
    ) -> AdapterExecutionResult:
        """Internal REAL dispatch path guarded by a module-private capability."""
        if capability is not _REAL_DISPATCH_CAPABILITY:
            raise PermissionError("capacidade de despacho REAL inválida.")
        if request.mode is not ExecutionMode.REAL:
            return AdapterExecutionResult(False, "execução REAL exige request REAL.", dispatch_attempted=False)
        return self._execute(broker, request)

    def _execute(self, broker: str, request: ExecutionRequest) -> AdapterExecutionResult:
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError as exc:
            return AdapterExecutionResult(False, str(exc), dispatch_attempted=False)

        try:
            available = bool(adapter.is_available())
        except Exception as exc:
            return AdapterExecutionResult(False, f"disponibilidade do adapter falhou: {exc}", dispatch_attempted=False)

        if not available:
            return AdapterExecutionResult(False, "adapter indisponível; execução não encaminhada.", dispatch_attempted=False)

        try:
            result = adapter.execute(request)
        except Exception as exc:
            # A transport/adapter exception is not a definitive rejection.
            # The request may have reached the broker before the exception, so
            # REAL execution must enter UNKNOWN rather than REJECTED.
            raise AdapterGatewayError(f"adapter falhou; execução não confirmada: {exc}") from exc

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.", dispatch_attempted=True)

        return AdapterExecutionResult(result.accepted, result.message, result, dispatch_attempted=True)
