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
    ambiguous: bool = False


class BrokerAdapterGateway:
    """Thin broker boundary; it never contains trading or signal logic."""

    def __init__(self, registry: BrokerRegistry) -> None:
        self._registry = registry

    def execute(self, broker: str, request: ExecutionRequest, *, expected_adapter_id: str | None = None) -> AdapterExecutionResult:
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

        if request.mode.value == "REAL":
            if not isinstance(expected_adapter_id, str) or not expected_adapter_id.strip():
                return AdapterExecutionResult(False, "execução REAL exige adapter_id autorizado.")
            actual_adapter_id = getattr(adapter, "adapter_id", None)
            if not isinstance(actual_adapter_id, str) or not actual_adapter_id.strip():
                return AdapterExecutionResult(False, "adapter REAL sem identidade explícita; dispatch bloqueado.")
            if actual_adapter_id.strip() != expected_adapter_id.strip():
                return AdapterExecutionResult(False, "adapter REAL diferente do adapter autorizado; dispatch bloqueado.")
            if getattr(adapter, "supports_real_execution", False) is not True:
                return AdapterExecutionResult(
                    False,
                    "adapter não possui opt-in explícito para execução REAL; dispatch bloqueado.",
                )
            # A REAL adapter must expose a broker-side correlation path capable of
            # locating an order by the canonical request_id after a crash that occurs
            # before external_id is returned/persisted. Without this capability,
            # accepting a REAL adapter would create an unrecoverable ambiguity window.
            if not callable(getattr(adapter, "query_order_by_request_id", None)):
                return AdapterExecutionResult(
                    False,
                    "adapter REAL sem correlação durável por request_id; dispatch bloqueado.",
                )

        try:
            result = adapter.execute(request)
        except Exception as exc:
            return AdapterExecutionResult(False, f"adapter falhou; execução não confirmada: {exc}", None, True)

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.")
        if result.accepted and (not isinstance(result.external_id, str) or not result.external_id.strip()):
            return AdapterExecutionResult(
                False,
                "adapter sinalizou aceite sem external_id; resultado ambíguo.",
                result,
                True,
            )

        return AdapterExecutionResult(result.accepted, result.message, result)
