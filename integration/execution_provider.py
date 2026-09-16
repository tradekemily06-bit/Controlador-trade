from __future__ import annotations

from execution.ports import ExecutionMode, ExecutionPort, ExecutionRequest, ExecutionResult
from execution.paper import PaperExecutor
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig


class ExecutionProviderConfigurationError(ValueError):
    """Raised when an unsupported execution provider is requested."""


class _DemoBrokerExecutionPort:
    """Broker-agnostic DEMO port that keeps the concrete adapter private."""

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


def build_demo_execution_port(provider: str = "paper", *, symbol: str | None = None) -> ExecutionPort:
    """Build a broker-agnostic DEMO execution port.

    The concrete broker adapter is created only inside this integration
    boundary and is never returned to callers. REAL is not a supported provider
    value and therefore cannot be activated through configuration.
    """
    normalized = provider.strip().lower() if isinstance(provider, str) else ""
    if normalized == "paper":
        return PaperExecutor()
    if normalized == "ic_markets_mt5_demo":
        adapter = ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol=symbol))
        return _DemoBrokerExecutionPort(adapter)
    raise ExecutionProviderConfigurationError(
        f"provedor de execução DEMO não suportado: {provider!r}"
    )
