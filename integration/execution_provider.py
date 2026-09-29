from __future__ import annotations

from execution.ports import ExecutionPort
from execution.paper import PaperExecutor
from execution.broker_registry import BrokerRegistry, BrokerRegistryError
from execution.default_registry import build_demo_registry


class ExecutionProviderConfigurationError(ValueError):
    """Raised when an unsupported execution provider is requested."""


def build_demo_execution_port(
    provider: str = "paper",
    *,
    symbol: str | None = None,
    registry: BrokerRegistry | None = None,
) -> ExecutionPort:
    """Build a DEMO executor through an opaque, externally extensible registry.

    ``paper`` remains the safe default. Concrete broker/platform adapters are
    selected by registry keys. Adding another adapter does not require changing
    this factory or the core; callers can register it at the integration edge
    and inject the registry here.
    """
    normalized = provider.strip().lower() if isinstance(provider, str) else ""
    if normalized == "paper":
        return PaperExecutor()

    selected_registry = registry or build_demo_registry(symbol=symbol)
    try:
        return selected_registry.get(normalized)
    except BrokerRegistryError as exc:
        raise ExecutionProviderConfigurationError(
            f"provedor de execução DEMO não suportado: {provider!r}"
        ) from exc
