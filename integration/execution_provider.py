from __future__ import annotations

from execution.ports import ExecutionPort
from execution.paper import PaperExecutor
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig
from execution.mt5_real_adapter import MT5RealAdapter, MT5RealConfig


class ExecutionProviderConfigurationError(ValueError):
    """Raised when an unsupported execution provider is requested."""


def build_demo_execution_port(provider: str = "paper", *, symbol: str | None = None) -> ExecutionPort:
    """Build an explicitly selected DEMO executor at the integration boundary."""
    normalized = provider.strip().lower() if isinstance(provider, str) else ""
    if normalized == "paper":
        return PaperExecutor()
    if normalized == "ic_markets_mt5_demo":
        return ICMarketsMT5DemoAdapter(ICMarketsMT5DemoConfig(symbol=symbol))
    raise ExecutionProviderConfigurationError(
        f"provedor de execução DEMO não suportado: {provider!r}"
    )


def build_real_execution_adapter(
    provider: str = "mt5_real",
    *,
    symbol: str | None = None,
    expected_server: str | None = None,
) -> ExecutionPort:
    """Build a REAL adapter without enabling or authorizing REAL execution.

    Authorization, admission, safety and explicit user confirmation remain
    responsibilities of the existing REAL execution boundaries.
    """
    normalized = provider.strip().lower() if isinstance(provider, str) else ""
    if normalized == "mt5_real":
        return MT5RealAdapter(
            MT5RealConfig(symbol=symbol, expected_server=expected_server)
        )
    raise ExecutionProviderConfigurationError(
        f"provedor de execução REAL não suportado: {provider!r}"
    )
