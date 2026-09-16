from __future__ import annotations

from typing import Any

from core.kill_switch import KillSwitch
from execution.broker_registry import BrokerRegistry, _BROKER_GATEWAY_CAPABILITY
from execution.gateway import ExecutionGateway
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig
from execution.mt5_demo_risk_state_provider import MT5DemoRiskStateConfig, MT5DemoRiskStateProvider

IC_MARKETS_MT5_DEMO = "ic_markets_mt5_demo"


def _build_demo_registry(*, mt5_module: Any = None, symbol: str | None = None) -> BrokerRegistry:
    """Internal composition helper; no public adapter factory is exported."""
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
    timeframe: int = 5,
    kill_switch: KillSwitch | None = None,
) -> ExecutionGateway:
    """Compose IC Markets MT5 DEMO behind the DEMO safety gateway.

    The adapter is created and consumed entirely inside this composition
    boundary. Callers receive only the broker-agnostic ExecutionGateway.
    """
    if not isinstance(timeframe, int) or isinstance(timeframe, bool) or timeframe <= 0:
        raise ValueError("timeframe deve ser um inteiro positivo")
    registry = _build_demo_registry(mt5_module=mt5_module, symbol=symbol)
    adapter = registry._get_for_gateway(
        IC_MARKETS_MT5_DEMO,
        capability=_BROKER_GATEWAY_CAPABILITY,
    )
    risk_provider = MT5DemoRiskStateProvider(
        MT5DemoRiskStateConfig(symbol=symbol, timeframe=timeframe),
        mt5_module=mt5_module,
    )
    return ExecutionGateway(
        adapter,
        kill_switch or KillSwitch(),
        risk_state_provider=risk_provider,
    )
