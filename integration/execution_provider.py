from __future__ import annotations

import os
from execution.ports import ExecutionPort
from execution.paper import PaperExecutor
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig, ICMarketsMT5RealAdapter


class ExecutionProviderConfigurationError(ValueError):
    """Raised when an unsupported execution provider is requested."""


def build_demo_execution_port(provider: str = "paper", *, symbol: str | None = None) -> ExecutionPort:
    """Build an explicitly selected executor at the integration boundary.

    The safe default remains PAPER. DEMO and REAL MT5 providers are explicit; REAL
    is only useful through the REAL gateway and manual confirmation path. No credentials are handled here.
    """
    normalized = provider.strip().lower() if isinstance(provider, str) else ""
    if normalized == "paper":
        return PaperExecutor()
    if normalized == "ic_markets_mt5_demo":
        risk_day_timezone = os.environ.get("CONTROLADOR_RISK_DAY_TIMEZONE", "UTC").strip() or "UTC"
        return ICMarketsMT5DemoAdapter(
            ICMarketsMT5DemoConfig(symbol=symbol, risk_day_timezone=risk_day_timezone)
        )
    if normalized == "ic_markets_mt5_real":
        risk_day_timezone = os.environ.get("CONTROLADOR_RISK_DAY_TIMEZONE", "UTC").strip() or "UTC"
        return ICMarketsMT5RealAdapter(
            ICMarketsMT5DemoConfig(symbol=symbol, risk_day_timezone=risk_day_timezone)
        )
    raise ExecutionProviderConfigurationError(
        f"provedor de execução não suportado: {provider!r}"
    )
