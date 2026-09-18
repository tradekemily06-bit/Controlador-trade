from __future__ import annotations

from dataclasses import dataclass

from core.p121_external_order_reconciliation import ExternalOrderQueryPort
from execution.broker_registry import BrokerRegistry, BrokerRegistryError
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class AdapterGatewayError(RuntimeError):
    """Raised when an adapter cannot safely receive an execution request."""


@dataclass(frozen=True)
class _RealDispatchCapability:
    adapter: object
    adapter_id: str


class _RealQueryCapability:
    """Broker query capability pinned to the authorized adapter instance."""

    def __init__(self, adapter: object, adapter_id: str) -> None:
        self._adapter = adapter
        self._adapter_id = adapter_id

    def _valid(self) -> bool:
        current_id = getattr(self._adapter, "adapter_id", None)
        return (
            isinstance(current_id, str)
            and current_id.strip().lower() == self._adapter_id.strip().lower()
            and bool(getattr(self._adapter, "supports_real_execution", False))
            and callable(getattr(self._adapter, "query_order", None))
        )

    def query_order(self, external_id: str):
        if not self._valid():
            raise ValueError("capacidade de consulta REAL mudou; reconciliação bloqueada.")
        result = self._adapter.query_order(external_id)
        if not self._valid():
            raise ValueError("capacidade de consulta REAL mudou durante a consulta; reconciliação bloqueada.")
        return result


_REAL_DISPATCH_CAPABILITY = None


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
        return self._dispatch(broker, request, require_real=False)

    def execute_real(
        self,
        broker: str,
        request: ExecutionRequest,
        *,
        capability: _RealDispatchCapability,
    ) -> AdapterExecutionResult:
        if not isinstance(capability, _RealDispatchCapability):
            return AdapterExecutionResult(False, "capacidade REAL inválida; dispatch bloqueado.")
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.REAL:
            return AdapterExecutionResult(
                False,
                "execute_real aceita somente ExecutionMode.REAL.",
            )
        try:
            current = self._registry.get(broker)
        except BrokerRegistryError as exc:
            return AdapterExecutionResult(False, str(exc))
        if current is not capability.adapter:
            return AdapterExecutionResult(False, "adapter REAL mudou após autorização; dispatch bloqueado.")
        current_id = getattr(current, "adapter_id", None)
        if not isinstance(current_id, str) or current_id.strip().lower() != capability.adapter_id.lower():
            return AdapterExecutionResult(False, "identidade do adapter REAL mudou após autorização; dispatch bloqueado.")
        return self._dispatch(
            broker,
            request,
            require_real=True,
            expected_adapter=capability.adapter,
        )

    def real_dispatch_capability(self, broker: str, *, expected_adapter_id: str) -> _RealDispatchCapability | None:
        if not isinstance(expected_adapter_id, str) or not expected_adapter_id.strip():
            return None
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError:
            return None
        if not bool(getattr(adapter, "supports_real_execution", False)):
            return None
        adapter_id = getattr(adapter, "adapter_id", None)
        if not isinstance(adapter_id, str) or adapter_id.strip().lower() != expected_adapter_id.strip().lower():
            return None
        return _RealDispatchCapability(adapter, adapter_id.strip())

    def real_adapter_id(self, broker: str) -> str | None:
        """Return the explicit identity bound to a REAL-capable adapter."""
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError:
            return None
        adapter_id = getattr(adapter, "adapter_id", None)
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            return None
        return adapter_id.strip()

    def real_query_port(self, broker: str, *, expected_adapter_id: str) -> ExternalOrderQueryPort | None:
        """Return reconciliation capability only from the authorized REAL adapter."""
        if not isinstance(expected_adapter_id, str) or not expected_adapter_id.strip():
            return None
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError:
            return None
        if not bool(getattr(adapter, "supports_real_execution", False)):
            return None
        adapter_id = getattr(adapter, "adapter_id", None)
        if not isinstance(adapter_id, str) or adapter_id.strip().lower() != expected_adapter_id.strip().lower():
            return None
        if not callable(getattr(adapter, "query_order", None)):
            return None
        if not isinstance(adapter, ExternalOrderQueryPort):
            return None
        return _RealQueryCapability(adapter, adapter_id.strip())

    def _dispatch(
        self,
        broker: str,
        request: ExecutionRequest,
        *,
        require_real: bool,
        expected_adapter: object | None = None,
    ) -> AdapterExecutionResult:
        try:
            adapter = self._registry.get(broker)
        except BrokerRegistryError as exc:
            return AdapterExecutionResult(False, str(exc))

        if expected_adapter is not None and adapter is not expected_adapter:
            return AdapterExecutionResult(False, "adapter REAL mudou durante o dispatch; execução bloqueada antes do adapter.execute.")

        if require_real:
            if not bool(getattr(adapter, "supports_real_execution", False)):
                return AdapterExecutionResult(
                    False,
                    "adapter não declara capacidade REAL; dispatch bloqueado antes do adapter.execute.",
                )
            adapter_id = getattr(adapter, "adapter_id", None)
            if not isinstance(adapter_id, str) or not adapter_id.strip():
                return AdapterExecutionResult(
                    False,
                    "adapter REAL sem identidade explícita; dispatch bloqueado antes do adapter.execute.",
                )

        try:
            available = bool(adapter.is_available())
        except Exception as exc:
            return AdapterExecutionResult(False, f"disponibilidade do adapter falhou: {exc}")

        if not available:
            return AdapterExecutionResult(False, "adapter indisponível; execução não encaminhada.")

        # is_available() is adapter code too. Revalidate the REAL capability
        # immediately before the irreversible adapter.execute() call so a
        # mutable adapter cannot change its identity/capability in between.
        if expected_adapter is not None:
            if adapter is not expected_adapter:
                return AdapterExecutionResult(
                    False,
                    "adapter REAL mudou durante a checagem de disponibilidade; execução bloqueada antes do adapter.execute.",
                )
            current_id = getattr(adapter, "adapter_id", None)
            expected_id = getattr(expected_adapter, "adapter_id", None)
            if (
                not isinstance(current_id, str)
                or not isinstance(expected_id, str)
                or current_id.strip().lower() != expected_id.strip().lower()
            ):
                return AdapterExecutionResult(
                    False,
                    "identidade do adapter REAL mudou durante a checagem de disponibilidade; execução bloqueada antes do adapter.execute.",
                )
            if not bool(getattr(adapter, "supports_real_execution", False)):
                return AdapterExecutionResult(
                    False,
                    "capacidade REAL do adapter mudou durante a checagem de disponibilidade; execução bloqueada antes do adapter.execute.",
                )

        try:
            result = adapter.execute(request)
        except Exception as exc:
            return AdapterExecutionResult(False, f"adapter falhou; execução não confirmada: {exc}")

        if not isinstance(result, ExecutionResult):
            return AdapterExecutionResult(False, "adapter retornou resultado inválido.")

        return AdapterExecutionResult(result.accepted, result.message, result)
