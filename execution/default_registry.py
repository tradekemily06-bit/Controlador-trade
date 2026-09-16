from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.kill_switch import KillSwitch
from core.operational_runtime import build_operational_runtime
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
    runtime_root: str | Path | None = None,
) -> ExecutionGateway:
    """Compose IC Markets MT5 DEMO only through the full operational runtime.

    This factory deliberately does not construct a bare ``ExecutionGateway``.
    The returned gateway therefore always owns the durable execution ledger,
    lifecycle state, maintenance state, safety store and cross-process dispatch
    lock supplied by ``build_operational_runtime``. The broker adapter remains
    private to this composition boundary.

    ``runtime_root`` may be supplied by the host. When omitted, the same
    ``CONTROLADOR_RUNTIME_DIR``/``.runtime`` convention used by the application
    runtime is used. Construction remains side-effect free with respect to MT5.
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

    root = Path(runtime_root) if runtime_root is not None else Path(
        os.environ.get("CONTROLADOR_RUNTIME_DIR", ".runtime")
    )
    runtime = build_operational_runtime(
        root,
        executor=adapter,
        risk_state_provider=risk_provider,
    )

    # Preserve the caller's explicit safety intent while keeping the durable
    # runtime-owned KillSwitch as the only switch consulted by the gateway.
    if kill_switch is not None:
        state = kill_switch.state
        if state.enabled:
            runtime.kill_switch.activate(state.reason or "kill switch externo ativado")

    return runtime.gateway
