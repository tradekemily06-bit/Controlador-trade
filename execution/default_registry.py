from __future__ import annotations

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


def build_demo_registry(*, mt5_module: Any = None, symbol: str | None = None, operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None) -> BrokerRegistry:
    """Build the private broker registry used by the DEMO execution boundary."""
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
    return GlobalOperationalBarrier((SafetyComponent(name="operational-runtime", healthy=False, detail="runtime operacional não foi fornecido ao gateway de execução"),))


def _compose_runtime_and_external_barriers(
    runtime,
    external_provider: Callable[[], GlobalOperationalBarrier],
) -> Callable[[], GlobalOperationalBarrier]:
    """Treat an injected barrier as an additional guard, never as an override."""
    from core.operational_barrier_factory import build_global_operational_barrier

    def provider() -> GlobalOperationalBarrier:
        runtime_decision = build_global_operational_barrier(runtime).evaluate()
        components = [
            SafetyComponent(
                name="authoritative-operational-runtime",
                healthy=runtime_decision.operationally_allowed,
                detail=runtime_decision.reason,
            )
        ]
        try:
            external = external_provider()
            if not isinstance(external, GlobalOperationalBarrier):
                components.append(
                    SafetyComponent(
                        name="external-operational-guard",
                        healthy=False,
                        detail="provedor externo retornou um objeto inválido",
                    )
                )
            else:
                external_decision = external.evaluate()
                components.append(
                    SafetyComponent(
                        name="external-operational-guard",
                        healthy=external_decision.operationally_allowed,
                        detail=external_decision.reason,
                    )
                )
        except Exception as exc:
            components.append(
                SafetyComponent(
                    name="external-operational-guard",
                    healthy=False,
                    detail=f"provedor externo indisponível: {type(exc).__name__}",
                )
            )
        return GlobalOperationalBarrier(tuple(components))

    return provider


def build_ic_markets_mt5_demo_gateway(*, mt5_module: Any = None, symbol: str | None = None, kill_switch: KillSwitch | None = None, operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None, market_data_fingerprint_provider: Callable[[], str | None] | None = None, risk_state_fingerprint_provider: Callable[[], str | None] | None = None, decision_freshness_policy: DecisionFreshnessPolicy | None = None, runtime_root: str | Path | None = None) -> ExecutionGateway:
    """Compose IC Markets MT5 DEMO through the durable operational runtime.

    Without runtime_root the factory is intentionally fail-closed. Supplying
    external providers alone can never turn the convenience factory into an
    operational gateway without durable ledger/lifecycle/safety composition.
    When a runtime exists, an injected barrier is an additional guard and can
    never replace or weaken the authoritative runtime barrier.
    """
    if runtime_root is None:
        registry = build_demo_registry(mt5_module=mt5_module, symbol=symbol, operational_barrier_provider=_missing_runtime_barrier)
        adapter = registry.get(IC_MARKETS_MT5_DEMO)
        return ExecutionGateway(adapter, kill_switch or KillSwitch(), operational_barrier_provider=_missing_runtime_barrier)

    root = Path(runtime_root)
    registry = build_demo_registry(mt5_module=mt5_module, symbol=symbol)
    adapter = registry.get(IC_MARKETS_MT5_DEMO)
    runtime = build_operational_runtime(root, executor=adapter, risk_state_fingerprint_provider=risk_state_fingerprint_provider)

    if kill_switch is not None and kill_switch.state.enabled:
        runtime.kill_switch.activate(kill_switch.state.reason or "kill switch externo ativado")
    if operational_barrier_provider is not None:
        runtime.gateway.set_operational_barrier_provider(
            _compose_runtime_and_external_barriers(runtime, operational_barrier_provider)
        )
    if market_data_fingerprint_provider is not None:
        runtime.gateway.set_market_data_fingerprint_provider(market_data_fingerprint_provider)
    if risk_state_fingerprint_provider is not None:
        runtime.gateway.set_risk_state_fingerprint_provider(risk_state_fingerprint_provider)
    if decision_freshness_policy is not None:
        runtime.gateway.set_decision_freshness_policy(decision_freshness_policy)
    return runtime.gateway
