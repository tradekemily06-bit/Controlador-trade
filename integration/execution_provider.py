from __future__ import annotations

from execution.ports import ExecutionPort
from execution.paper import PaperExecutor
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig


class ExecutionProviderConfigurationError(ValueError):
    """Raised when an unsupported execution provider is requested."""


def build_demo_execution_port(provider: str = "paper", *, symbol: str | None = None) -> ExecutionPort:
    """Build an explicitly selected DEMO executor at the integration boundary.

    The safe default remains PAPER. IC Markets MT5 is opt-in and still accepts
    only DEMO requests inside its own adapter. No credentials are handled here.
    """
    normalized = provider.strip().lower() if isinstance(provider, str) else ""
    if normalized == "paper":
        return PaperExecutor()
    if normalized == "ic_markets_mt5_demo":
        return ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol=symbol))
    raise ExecutionProviderConfigurationError(
        f"provedor de execução DEMO não suportado: {provider!r}"
    )
