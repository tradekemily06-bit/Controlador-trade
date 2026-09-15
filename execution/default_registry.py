from __future__ import annotations

from typing import Any, Callable

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
    """Return a deliberately blocking barrier when no runtime was supplied.

    This helper can construct an adapter for tests/integration composition, but
    it must never become an operational bypass around the authoritative runtime
    barrier. A caller with a real runtime must explicitly provide its barrier.
    """
    return GlobalOperationalBarrier(
        (
            SafetyComponent(
                name="operational-runtime",
                healthy=False,
                detail="runtime operacional não foi fornecido ao gateway de execução",
            ),
        )
    )


def build_ic_markets_mt5_demo_gateway(
    *,
    mt5_module: Any = None,
    symbol: str | None = None,
    kill_switch: KillSwitch | None = None,
    operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None,
) -> ExecutionGateway:
    """Compose the IC Markets MT5 DEMO adapter behind the safety gateway.

    Construction is side-effect free. The MT5 terminal is not initialized and
    no order can be sent until the returned gateway receives an explicit DEMO
    execution request that passes its safety checks.

    If an authoritative runtime barrier provider is not supplied, the gateway
    is intentionally fail-closed. This prevents this convenience constructor
    from becoming a production bypass of the global operational barrier.
    """
    registry = build_demo_registry(mt5_module=mt5_module, symbol=symbol)
    adapter = registry.get(IC_MARKETS_MT5_DEMO)
    provider = operational_barrier_provider or _missing_runtime_barrier
    return ExecutionGateway(
        adapter,
        kill_switch or KillSwitch(),
        operational_barrier_provider=provider,
    )
