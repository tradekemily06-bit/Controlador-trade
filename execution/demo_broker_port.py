from __future__ import annotations

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionPort, ExecutionResult


# Capability is intentionally module-private. The runtime-bound wrapper is the
# only in-tree caller that receives it, preventing a public method call from
# becoming a broker-dispatch side door.
_DEMO_GATEWAY_CAPABILITY = object()


class DemoBrokerExecutionPort:
    """Broker-bound DEMO port whose public execute method cannot dispatch directly."""

    def __init__(self, adapter: ICMarketsMT5DemoAdapter) -> None:
        if not isinstance(adapter, ICMarketsMT5DemoAdapter):
            raise ValueError("adapter DEMO inválido")
        self.__adapter = adapter

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "porta DEMO rejeitou requisição fora do modo DEMO")
        return ExecutionResult(False, "dispatch direto do broker DEMO bloqueado; use o gateway operacional")

    def execute_from_gateway(self, request: ExecutionRequest, *, capability: object) -> ExecutionResult:
        if capability is not _DEMO_GATEWAY_CAPABILITY:
            raise PermissionError("dispatch DEMO exige a capacidade do gateway operacional")
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "porta DEMO rejeitou requisição fora do modo DEMO")
        return self.__adapter.execute(request)

    def is_available(self) -> bool:
        return bool(self.__adapter.is_available())


class GatewayBoundDemoExecutionPort:
    """Internal runtime binding that exposes broker dispatch only to the gateway."""

    def __init__(self, port: DemoBrokerExecutionPort) -> None:
        if not isinstance(port, DemoBrokerExecutionPort):
            raise ValueError("porta DEMO inválida")
        self._port = port

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return self._port.execute_from_gateway(request, capability=_DEMO_GATEWAY_CAPABILITY)

    def is_available(self) -> bool:
        return self._port.is_available()


def build_ic_markets_mt5_demo_port(*, symbol: str | None = None) -> ExecutionPort:
    """Create the IC Markets MT5 DEMO port without exposing its adapter."""
    return DemoBrokerExecutionPort(
        ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol=symbol))
    )
