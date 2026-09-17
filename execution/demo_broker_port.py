from __future__ import annotations

from typing import Any

from execution.icmarkets_mt5_demo_adapter import (
    ICMarketsMT5DemoAdapter,
    ICMarketsMT5DemoConfig,
    _DEMO_ADAPTER_CAPABILITY,
)
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionPort, ExecutionResult


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
        return self.__adapter.execute_from_port(request, capability=_DEMO_ADAPTER_CAPABILITY)

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


def build_ic_markets_mt5_demo_adapter(*, symbol: str | None = None, mt5_module: Any = None) -> ICMarketsMT5DemoAdapter:
    """Construct a raw adapter only for the broker-port composition boundary."""
    return ICMarketsMT5DemoAdapter(
        ICMarketsMT5DemoConfig(symbol=symbol),
        mt5_module=mt5_module,
    )


def build_ic_markets_mt5_demo_port(*, symbol: str | None = None, mt5_module: Any = None) -> ExecutionPort:
    """Create the IC Markets MT5 DEMO port without exposing its adapter."""
    return DemoBrokerExecutionPort(
        build_ic_markets_mt5_demo_adapter(symbol=symbol, mt5_module=mt5_module)
    )
