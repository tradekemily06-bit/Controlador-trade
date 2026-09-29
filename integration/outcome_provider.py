from __future__ import annotations

from typing import Any

from core.operation_lineage import OperationLineageStore
from execution.external_outcome_port import ExternalOutcomePort
from execution.icmarkets_mt5_demo_outcome import ICMarketsMT5DemoOutcomeBridge
from execution.mt5_external_outcome_adapter import MT5ExternalOutcomeAdapter
from execution.outcome_registry import ExternalOutcomeRegistry, OutcomeRegistryError


class OutcomeProviderConfigurationError(ValueError):
    """Raised when a DEMO outcome provider cannot be resolved safely."""


def build_demo_outcome_registry(
    *,
    lineage: OperationLineageStore,
    mt5_module: Any = None,
) -> ExternalOutcomeRegistry:
    """Build the default outcome registry at the integration edge.

    Concrete providers are registered here, never inside core contracts.
    Future adapters can be supplied through an external registry without
    changing the generic service or learning path.
    """
    if lineage is None:
        raise ValueError("lineage é obrigatório.")
    registry = ExternalOutcomeRegistry()
    mt5_bridge = ICMarketsMT5DemoOutcomeBridge(
        lineage=lineage,
        mt5_module=mt5_module,
    )
    registry.register(
        "ic_markets_mt5_demo",
        MT5ExternalOutcomeAdapter(mt5_bridge),
    )
    return registry


def build_external_outcome_port(
    provider: str,
    *,
    lineage: OperationLineageStore,
    mt5_module: Any = None,
    registry: ExternalOutcomeRegistry | None = None,
) -> ExternalOutcomePort:
    normalized = provider.strip().lower() if isinstance(provider, str) else ""
    if not normalized or normalized == "paper":
        raise OutcomeProviderConfigurationError(
            "o modo paper não possui fechamento/resultado externo; selecione um adapter DEMO."
        )

    selected = registry or build_demo_outcome_registry(
        lineage=lineage,
        mt5_module=mt5_module,
    )
    try:
        return selected.get(normalized)
    except OutcomeRegistryError as exc:
        raise OutcomeProviderConfigurationError(
            f"provedor de resultado externo não suportado: {provider!r}"
        ) from exc


# Compatibility API. The returned contract is mode-neutral and can be used by DEMO or REAL adapters.
build_demo_outcome_port = build_external_outcome_port
