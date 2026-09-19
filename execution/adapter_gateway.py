from __future__ import annotations

from dataclasses import dataclass
import math

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
        if not isinstance(broker, str) or not broker.strip() or len(broker.strip()) > 64:
            return AdapterExecutionResult(False, "broker inválido.")
        if not isinstance(request, ExecutionRequest):
            return AdapterExecutionResult(False, "requisição de execução inválida.")
        if not isinstance(request.request_id, str) or not request.request_id.strip() or len(request.request_id.strip()) > 128:
            return AdapterExecutionResult(False, "request_id inválido.")
        if not isinstance(request.symbol, str) or not request.symbol.strip() or len(request.symbol.strip()) > 64:
            return AdapterExecutionResult(False, "símbolo inválido.")
        if not isinstance(request.amount, (int, float)) or isinstance(request.amount, bool) or not math.isfinite(float(request.amount)) or request.amount <= 0:
            return AdapterExecutionResult(False, "valor de execução inválido.")
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0 or request.duration_seconds > 86_400:
            return AdapterExecutionResult(False, "duração inválida.")
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError as exc:
            return AdapterExecutionResult(False, str(exc))

        try:
            available = adapter.is_available()
        except Exception:
            return AdapterExecutionResult(False, "disponibilidade do adapter falhou.")

        if not isinstance(available, bool):
            return AdapterExecutionResult(False, "adapter retornou disponibilidade inválida.")
        if not available:
            return AdapterExecutionResult(False, "adapter indisponível; execução não encaminhada.")

        try:
            result = adapter.execute(request)
        except Exception as exc:
            return AdapterExecutionResult(False, f"adapter falhou; execução não confirmada: {type(exc).__name__}")

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.")
        if not isinstance(result.accepted, bool) or not isinstance(result.uncertain, bool):
            return AdapterExecutionResult(False, "adapter retornou flags de execução inválidas.")
        if not isinstance(result.message, str) or not result.message.strip() or len(result.message) > 4096:
            return AdapterExecutionResult(False, "adapter retornou mensagem inválida.")
        if result.external_id is not None and (
            not isinstance(result.external_id, str)
            or not result.external_id.strip()
            or len(result.external_id.strip()) > 256
        ):
            return AdapterExecutionResult(False, "adapter retornou identificador externo inválido.")

        return AdapterExecutionResult(result.accepted, result.message, result)
