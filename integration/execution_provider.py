from __future__ import annotations

from execution.demo_broker_port import build_ic_markets_mt5_demo_port
from execution.ports import ExecutionPort
from execution.paper import PaperExecutor


class ExecutionProviderConfigurationError(ValueError):
    """Raised when an unsupported execution provider is requested."""


def build_demo_execution_port(provider: str = "paper", *, symbol: str | None = None) -> ExecutionPort:
    """Build a broker-agnostic DEMO execution port.

    Concrete broker adapters remain inside the execution boundary and are
    never returned to integration/application callers. REAL is not a supported
    provider value and therefore cannot be activated through configuration.
    """
    normalized = provider.strip().lower() if isinstance(provider, str) else ""
    if normalized == "paper":
        return PaperExecutor()
    if normalized == "ic_markets_mt5_demo":
        return build_ic_markets_mt5_demo_port(symbol=symbol)
    raise ExecutionProviderConfigurationError(
        f"provedor de execução DEMO não suportado: {provider!r}"
    )
