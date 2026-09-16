from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from core.decision_freshness import DecisionFreshnessPolicy
from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.kill_switch import KillSwitch
from core.operational_runtime import build_operational_runtime
from execution.broker_registry import BrokerRegistry
from execution.gateway import ExecutionGateway
from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter, ICMarketsMT5DemoConfig

IC_MARKETS_MT5_DEMO = "ic_markets_mt5_demo"


def build_demo_registry(
    *,
    mt5_module: Any = None,
    symbol: str | None = None,
    operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None,
) -> BrokerRegistry:
    """Build the private broker registry used by the DEMO execution boundary.

    Registration is side-effect free. The registry must not be treated as an
    operational runtime or as a source of durable execution authority.
    """
    registry = BrokerRegistry()
    registry.register(
        IC_MARKETS_MT5_DEMO,
        ICMarketsMT5DemoAdapter(
            ICMarketsMT5DemoConfig(symbol=symbol),
            mt5_module=mt5_module,
            operational_barrier_provider=operational_barrier_provider,
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
                detail="contexto operacional incompleto; gateway não pode executar",
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
    runtime_root: str | Path | None = None,
) -> ExecutionGateway:
    """Compose IC Markets MT5 DEMO only through the durable operational runtime.

    A runtime root is required for an operationally usable gateway because the
    runtime owns the durable ledger, lifecycle state, safety state and the
    cross-process dispatch lock. Without one, this convenience factory returns
    a deliberately blocking gateway rather than creating a bypass gateway.
    """
    if runtime_root is None:
        required_context_missing = (
            operational_barrier_provider is None
            or market_data_fingerprint_provider is None
            or risk_state_fingerprint_provider is None
            or decision_freshness_policy is None
        )
        provider = (
            _missing_runtime_barrier
            if operational_barrier_provider is None
            else _missing_execution_context_barrier
            if required_context_missing
            else operational_barrier_provider
        )
        registry = build_demo_registry(
            mt5_module=mt5_module,
            symbol=symbol,
            operational_barrier_provider=provider,
        )
        adapter = registry.get(IC_MARKETS_MT5_DEMO)
        return ExecutionGateway(
            adapter,
            kill_switch or KillSwitch(),
            operational_barrier_provider=provider,
        )

    root = Path(runtime_root)
    registry = build_demo_registry(mt5_module=mt5_module, symbol=symbol)
    adapter = registry.get(IC_MARKETS_MT5_DEMO)
    runtime = build_operational_runtime(
        root,
        executor=adapter,
        risk_state_fingerprint_provider=risk_state_fingerprint_provider,
    )

    if kill_switch is not None and kill_switch.state.enabled:
        runtime.kill_switch.activate(kill_switch.state.reason or "kill switch externo ativado")
    if operational_barrier_provider is not None:
        runtime.gateway.set_operational_barrier_provider(operational_barrier_provider)
    if market_data_fingerprint_provider is not None:
        runtime.gateway.set_market_data_fingerprint_provider(market_data_fingerprint_provider)
    if risk_state_fingerprint_provider is not None:
        runtime.gateway.set_risk_state_fingerprint_provider(risk_state_fingerprint_provider)
    if decision_freshness_policy is not None:
        runtime.gateway.set_decision_freshness_policy(decision_freshness_policy)

    return runtime.gateway
