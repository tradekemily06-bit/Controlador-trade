from __future__ import annotations

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig
from execution.ports import ExecutionMode, ExecutionPort, ExecutionRequest, ExecutionResult


class DemoBrokerExecutionPort:
    """Broker-agnostic DEMO port that keeps the concrete adapter private.

    This object is intentionally placed inside the execution boundary. Higher
    layers receive only the ExecutionPort contract and cannot obtain the
    concrete broker adapter from the provider factory.
    """

    def __init__(self, adapter: ICMarketsMT5DemoAdapter) -> None:
        if not isinstance(adapter, ICMarketsMT5DemoAdapter):
            raise ValueError("adapter DEMO inválido")
        self.__adapter = adapter

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
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
