from __future__ import annotations

from typing import Any

from execution.broker_registry import BrokerRegistry
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
