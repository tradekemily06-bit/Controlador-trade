from __future__ import annotations

import math
from dataclasses import dataclass

from core.models import Signal
from core.request_identity import validate_request_id
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
    """Defense-in-depth broker boundary with explicit REAL authorization handoff."""

    def __init__(self, registry: BrokerRegistry) -> None:
        if not isinstance(registry, BrokerRegistry):
            raise ValueError("registry inválido.")
        self._registry = registry

    def adapter_id(self, broker: str) -> str:
        return self._registry.adapter_id(broker)

    @staticmethod
    def _validate(request: ExecutionRequest) -> str | None:
        if not isinstance(request, ExecutionRequest):
            return "requisição de execução inválida."
        if request.signal not in (Signal.COMPRA, Signal.VENDA):
            return "AGUARDAR não pode chegar ao adapter."
        try:
            validate_request_id(request.request_id)
        except ValueError:
            return "request_id inválido."
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return "symbol inválido."
        if isinstance(request.amount, bool) or not isinstance(request.amount, (int, float)) or not math.isfinite(float(request.amount)) or request.amount <= 0:
            return "amount inválido."
        if isinstance(request.duration_seconds, bool) or not isinstance(request.duration_seconds, int) or request.duration_seconds <= 0:
            return "duration_seconds inválido."
        return None

    def execute(self, broker: str, request: ExecutionRequest, *, allow_real: bool = False) -> AdapterExecutionResult:
        validation_error = self._validate(request)
        if validation_error is not None:
            return AdapterExecutionResult(False, validation_error)
        if request.mode is ExecutionMode.REAL and not allow_real:
            return AdapterExecutionResult(False, "REAL exige handoff explícito do RealExecutionGateway.")
        if request.mode not in (ExecutionMode.DEMO, ExecutionMode.REAL):
            return AdapterExecutionResult(False, "modo de execução inválido.")
        if not isinstance(broker, str) or not broker.strip():
            return AdapterExecutionResult(False, "broker inválido.")
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError:
            return AdapterExecutionResult(False, "broker/adapter não registrado.")
        try:
            available = bool(adapter.is_available())
        except Exception:
            return AdapterExecutionResult(False, "disponibilidade do adapter falhou.")
        if not available:
            return AdapterExecutionResult(False, "adapter indisponível; execução não encaminhada.")
        try:
            result = adapter.execute(request)
        except Exception:
            # Never expose adapter exception text: broker SDKs can embed URLs,
            # account data, request payloads or authentication material.
            return AdapterExecutionResult(False, "adapter falhou; execução não confirmada.")
        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.")
        return AdapterExecutionResult(result.accepted, result.message, result)
