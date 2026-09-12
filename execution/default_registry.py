from __future__ import annotations

from typing import Any

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


def build_ic_markets_mt5_demo_gateway(
    *,
    mt5_module: Any = None,
    symbol: str | None = None,
    kill_switch: KillSwitch | None = None,
) -> ExecutionGateway:
    """Compose the IC Markets MT5 DEMO adapter behind the safety gateway.

    Construction is side-effect free. The MT5 terminal is not initialized and
    no order can be sent until the returned gateway receives an explicit DEMO
    execution request that passes its safety checks.
    """
    registry = build_demo_registry(mt5_module=mt5_module, symbol=symbol)
    adapter = registry.get(IC_MARKETS_MT5_DEMO)
    return ExecutionGateway(adapter, kill_switch or KillSwitch())
