from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from execution.broker_registry import BrokerRegistry, BrokerRegistryError
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


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
        if not isinstance(request, ExecutionRequest):
            return AdapterExecutionResult(False, "requisição de execução inválida.")
        if request.mode is not ExecutionMode.DEMO:
            return AdapterExecutionResult(False, "REAL só pode atravessar a fronteira RealExecutionGateway.")
        return self._dispatch(broker, request)

    def adapter_id(self, broker: str) -> str | None:
        try:
            return self._registry.adapter_id(broker)
        except BrokerRegistryError:
            return None

    def _execute_real(
        self,
        broker: str,
        request: ExecutionRequest,
        *,
        final_guard: Callable[[], bool] | None = None,
    ) -> AdapterExecutionResult:
        """Internal REAL dispatch used only after RealExecutionGateway admission."""
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.REAL:
            return AdapterExecutionResult(False, "dispatch REAL interno recebeu requisição inválida.")
        return self._dispatch(broker, request, final_guard=final_guard)

    def _dispatch(
        self,
        broker: str,
        request: ExecutionRequest,
        *,
        final_guard: Callable[[], bool] | None = None,
    ) -> AdapterExecutionResult:
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

        # Final guard sits after adapter availability checks and immediately
        # before the external adapter call. It cannot make the check atomic
        # with the broker call, but it closes the avoidable application-side
        # gap where the live kill switch changes during preflight.
        if final_guard is not None:
            try:
                if not bool(final_guard()):
                    return AdapterExecutionResult(False, "dispatch externo bloqueado pela guarda final de segurança.")
            except Exception as exc:
                return AdapterExecutionResult(False, f"guarda final de segurança falhou: {type(exc).__name__}")

        try:
            result = adapter.execute(request)
        except Exception as exc:
            return AdapterExecutionResult(False, f"adapter falhou; execução não confirmada: {exc}")

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.")

        return AdapterExecutionResult(result.accepted, result.message, result)
