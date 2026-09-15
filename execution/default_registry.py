from __future__ import annotations

from typing import Any, Callable

from core.decision_freshness import DecisionFreshnessPolicy
from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.kill_switch import KillSwitch
from execution.broker_registry import BrokerRegistry
from execution.gateway import ExecutionGateway
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig

IC_MARKETS_MT5_DEMO = "ic_markets_mt5_demo"


def build_demo_registry(*, mt5_module: Any = None, symbol: str | None = None) -> BrokerRegistry:
    """Build the broker registry used by the DEMO execution boundary.

    Registration is local and side-effect free: creating the registry does not
    initialize MT5 or place an order. Runtime availability is checked only when
    the adapter/gateway is actually asked to execute or report availability.
    """
    registry = BrokerRegistry()
    registry.register(
        IC_MARKETS_MT5_DEMO,
        ICMarketsMT5DemoAdapter(
            ICMarketsMT5DemoConfig(symbol=symbol),
            mt5_module=mt5_module,
        ),
    )
    return registry


def _missing_runtime_barrier() -> GlobalOperationalBarrier:
    """Return a deliberately blocking barrier when no runtime was supplied."""
    return GlobalOperationalBarrier(
        (
            SafetyComponent(
                name="operational-runtime",
                healthy=False,
                detail="runtime operacional não foi fornecido ao gateway de execução",
            ),
        )
    )


def _missing_execution_context_barrier() -> GlobalOperationalBarrier:
    """Block the broker gateway until the complete execution context is wired."""
    return GlobalOperationalBarrier(
        (
            SafetyComponent(
                name="execution-context",
                healthy=False,
                detail="contexto de mercado, risco e frescor da decisão não foi fornecido ao gateway",
            ),
        )
    )


def build_ic_markets_mt5_demo_gateway(
    *,
    mt5_module: Any = None,
    symbol: str | None = None,
    kill_switch: KillSwitch | None = None,
    operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None,
    market_data_fingerprint_provider: Callable[[], str | None] | None = None,
    risk_state_fingerprint_provider: Callable[[], str | None] | None = None,
    decision_freshness_policy: DecisionFreshnessPolicy | None = None,
) -> ExecutionGateway:
    """Compose the IC Markets MT5 DEMO adapter behind the full safety boundary.

    Construction is side-effect free. The MT5 terminal is not initialized and
    no order can be sent until the returned gateway receives an explicit DEMO
    execution request that passes the operational barrier, market identity,
    risk identity and decision-freshness checks.

    The convenience constructor intentionally fails closed when any required
    runtime context is absent. This prevents a direct broker gateway from
    becoming a bypass around the production runtime's decision identity and
    risk/market freshness protections.
    """
    registry = build_demo_registry(mt5_module=mt5_module, symbol=symbol)
    adapter = registry.get(IC_MARKETS_MT5_DEMO)

    required_context_missing = (
        operational_barrier_provider is None
        or market_data_fingerprint_provider is None
        or risk_state_fingerprint_provider is None
        or decision_freshness_policy is None
    )
    if required_context_missing:
        provider = _missing_runtime_barrier if operational_barrier_provider is None else _missing_execution_context_barrier
    else:
        provider = operational_barrier_provider

    gateway = ExecutionGateway(
        adapter,
        kill_switch or KillSwitch(),
        operational_barrier_provider=provider,
    )
    if required_context_missing:
        # The blocking barrier is authoritative for this composition path, so
        # no partial context is exposed as operationally usable state.
        return gateway

    gateway.set_market_data_fingerprint_provider(market_data_fingerprint_provider)
    gateway.set_risk_state_fingerprint_provider(risk_state_fingerprint_provider)
    gateway.set_decision_freshness_policy(decision_freshness_policy)
    return gateway
