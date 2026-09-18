from __future__ import annotations

from dataclasses import dataclass

from execution.broker_registry import BrokerRegistry, BrokerRegistryError
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class AdapterGatewayError(RuntimeError):
    """Raised when an adapter cannot safely receive an execution request."""


class _RealDispatchCapability:
    pass


_REAL_DISPATCH_CAPABILITY = _RealDispatchCapability()


@dataclass(frozen=True)
class AdapterExecutionResult:
    accepted: bool
    message: str
    execution: ExecutionResult | None = None


class BrokerAdapterGateway:
    """Single adapter dispatch boundary.

    DEMO/PAPER may use execute(). REAL can only cross this boundary through
    execute_real(), which is called by RealExecutionGateway.
    """

    def __init__(self, registry: BrokerRegistry) -> None:
        if not isinstance(registry, BrokerRegistry):
            raise ValueError("registry inválido.")
        self._registry = registry

    def execute(self, broker: str, request: ExecutionRequest) -> AdapterExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return AdapterExecutionResult(False, "requisição inválida.")
        if request.mode is ExecutionMode.REAL:
            return AdapterExecutionResult(
                False,
                "REAL exige RealExecutionGateway; dispatch direto bloqueado.",
            )
        return self._dispatch(broker, request)

    def execute_real(
        self,
        broker: str,
        request: ExecutionRequest,
        *,
        capability: _RealDispatchCapability,
    ) -> AdapterExecutionResult:
        if capability is not _REAL_DISPATCH_CAPABILITY:
            return AdapterExecutionResult(
                False,
                "capacidade REAL inválida; dispatch bloqueado.",
            )
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.REAL:
            return AdapterExecutionResult(
                False,
                "execute_real aceita somente ExecutionMode.REAL.",
            )
        return self._dispatch(broker, request, require_real=True)

    def _dispatch(
        self,
        broker: str,
        request: ExecutionRequest,
        *,
        require_real: bool,
    ) -> AdapterExecutionResult:
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError as exc:
            return AdapterExecutionResult(False, str(exc))

        if require_real and not bool(getattr(adapter, "supports_real_execution", False)):
            return AdapterExecutionResult(
                False,
                "adapter não declara capacidade REAL; dispatch bloqueado antes do adapter.execute.",
            )

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
