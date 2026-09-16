from __future__ import annotations

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionPort, ExecutionResult


class DemoBrokerExecutionPort:
    """Broker-bound DEMO port whose public execute method cannot dispatch directly.

    The concrete adapter is private. Actual broker-side dispatch is exposed only
    through ``execute_from_gateway``, which the authoritative ExecutionGateway
    recognizes as an internal execution capability.
    """

    def __init__(self, adapter: ICMarketsMT5DemoAdapter) -> None:
        if not isinstance(adapter, ICMarketsMT5DemoAdapter):
            raise ValueError("adapter DEMO inválido")
        self.__adapter = adapter

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "porta DEMO rejeitou requisição fora do modo DEMO")
        return ExecutionResult(False, "dispatch direto do broker DEMO bloqueado; use o gateway operacional")

    def execute_from_gateway(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest) or request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "porta DEMO rejeitou requisição fora do modo DEMO")
        return self.__adapter.execute(request)

    def is_available(self) -> bool:
        return bool(self.__adapter.is_available())


def build_ic_markets_mt5_demo_port(*, symbol: str | None = None) -> ExecutionPort:
    """Create the IC Markets MT5 DEMO port without exposing its adapter."""
    return DemoBrokerExecutionPort(
        ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol=symbol))
    )
