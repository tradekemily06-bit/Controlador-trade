from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core.decision_audit import DecisionAudit
from core.decision_freshness import DecisionFreshnessPolicy
from core.demo_risk_state_store import DemoRiskStateStore
from core.ecosystem_incidents import EcosystemIncidentManager
from core.ecosystem_maintenance import MaintenanceManager
from core.kill_switch import KillSwitch
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from core.operational_safety_store import OperationalSafetyStore
from core.p21_observability import RuntimeHealthMonitor
from core.recovery_coordinator import RecoveryCoordinator
from core.risk_state_provider import RiskStateProvider
from core.runtime_checkpoint import RuntimeCheckpointStore
from core.technical_incident_store import TechnicalIncidentStore
from execution.demo_broker_port import DemoBrokerExecutionPort, GatewayBoundDemoExecutionPort
from execution.demo_risk_dispatch_guard import DemoRiskDispatchGuard
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from execution.gateway import ExecutionGateway
from execution.ports import ExecutionPort
from execution.paper import PaperExecutor


@dataclass(frozen=True)
class OperationalRuntime:
    """Single authoritative DEMO runtime state shared by execution and observability."""
    kill_switch: KillSwitch
    maintenance: MaintenanceManager
    incident_manager: EcosystemIncidentManager
    incident_store: TechnicalIncidentStore
    execution_ledger: ExecutionLedger
    execution_lifecycle: ExecutionLifecycleStore
    checkpoint_store: RuntimeCheckpointStore
    recovery: RecoveryCoordinator
    health: RuntimeHealthMonitor
    gateway: ExecutionGateway
    market_data: MarketDataRuntimeState
    safety_store: OperationalSafetyStore
    safety_audit: DecisionAudit
    demo_risk_state: DemoRiskStateStore | None = None
    risk_state_provider: RiskStateProvider | None = None

    @property
    def demo_risk_state_store(self) -> DemoRiskStateStore | None:
        """Compatibility name for the single authoritative DEMO risk store."""
        return self.demo_risk_state


def _public_saas_multi_instance() -> bool:
    public = os.environ.get("CONTROLADOR_SAAS_PUBLIC", "").strip().lower() in {"1", "true", "yes", "on"}
    multi_instance = os.environ.get("CONTROLADOR_MULTI_INSTANCE", "").strip().lower() in {"1", "true", "yes", "on"}
    return public and multi_instance


def build_operational_runtime(
    root: str | Path,
    executor: ExecutionPort | None = None,
    *,
    risk_state_provider: RiskStateProvider | None = None,
) -> OperationalRuntime:
    """Compose one authoritative, fail-closed operational runtime."""
    if _public_saas_multi_instance():
        raise RuntimeError("multi-instance public SaaS requires a shared authoritative operational state provider")

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    safety_store = OperationalSafetyStore(root / "operational-safety.json")
    demo_risk_state = DemoRiskStateStore(root / "demo-risk-state.json")
    try:
        safety_audit, persisted_switch = safety_store.load()
        initial_enabled = persisted_switch.enabled
        initial_reason = persisted_switch.reason
        safety_state_valid = True
    except (OSError, ValueError, TypeError) as exc:
        safety_audit = DecisionAudit()
        initial_enabled = True
        initial_reason = f"estado de segurança indisponível: {type(exc).__name__}"
        safety_state_valid = False

    kill_switch = KillSwitch()
    if initial_enabled:
        kill_switch.activate(initial_reason or "estado de segurança persistido")

    def persist_safety(_state) -> None:
        safety_store.save(safety_audit, kill_switch)

    kill_switch.set_on_change(persist_safety)
    if not safety_state_valid:
        safety_store.replace_with_fail_closed_state(initial_reason or "estado de segurança indisponível")
    elif not initial_enabled:
        safety_store.save(safety_audit, kill_switch)

    maintenance = MaintenanceManager(root / "maintenance.json")
    incident_store = TechnicalIncidentStore(root / "technical-incident.json")
    incident_manager = EcosystemIncidentManager(store=incident_store)
    ledger = ExecutionLedger(root / "execution-ledger.json")
    lifecycle = ExecutionLifecycleStore(root / "execution-lifecycle.json")
    checkpoint = RuntimeCheckpointStore(root / "runtime-checkpoint.json")
    recovery = RecoveryCoordinator(checkpoint_store=checkpoint, lifecycle_store=lifecycle, execution_ledger=ledger)
    health = RuntimeHealthMonitor(ledger=ledger, lifecycle=lifecycle, checkpoint_store=checkpoint, recovery=recovery)
    market_data = MarketDataRuntimeState(MarketDataRuntimeIntegrity())

    if executor is None:
        effective_executor: ExecutionPort = DemoRiskDispatchGuard(
            PaperExecutor(),
            risk_store=demo_risk_state,
            risk_fingerprint_provider=demo_risk_state.fingerprint,
        )
        # The default PAPER path has one authoritative DEMO risk store. The same
        # store is therefore bound to both the dispatch guard and the gateway's
        # final risk-state barrier; an explicitly supplied provider may replace
        # it when the caller owns an authoritative external source.
        runtime_risk_provider = risk_state_provider or demo_risk_state
    elif isinstance(executor, PaperExecutor):
        effective_executor = DemoRiskDispatchGuard(
            executor,
            risk_store=demo_risk_state,
            risk_fingerprint_provider=demo_risk_state.fingerprint,
        )
        runtime_risk_provider = risk_state_provider or demo_risk_state
    elif isinstance(executor, DemoBrokerExecutionPort):
        if risk_state_provider is None:
            raise RuntimeError("broker DEMO execution requires an authoritative risk-state provider")
        effective_executor = GatewayBoundDemoExecutionPort(executor)
        runtime_risk_provider = risk_state_provider
    else:
        raise RuntimeError(
            "executor operacional não autorizado; use PaperExecutor ou DemoBrokerExecutionPort"
        )

    gateway = ExecutionGateway(
        effective_executor,
        kill_switch,
        ledger=ledger,
        lifecycle=lifecycle,
        maintenance=maintenance,
        safety_store=safety_store,
        incident_manager=incident_manager,
        risk_state_provider=runtime_risk_provider,
    )
    runtime = OperationalRuntime(
        kill_switch=kill_switch,
        maintenance=maintenance,
        incident_manager=incident_manager,
        incident_store=incident_store,
        execution_ledger=ledger,
        execution_lifecycle=lifecycle,
        checkpoint_store=checkpoint,
        recovery=recovery,
        health=health,
        gateway=gateway,
        market_data=market_data,
        safety_store=safety_store,
        safety_audit=safety_audit,
        demo_risk_state=demo_risk_state,
        risk_state_provider=runtime_risk_provider,
    )

    from core.operational_barrier_factory import build_global_operational_barrier
    gateway.set_operational_barrier_provider(lambda: build_global_operational_barrier(runtime))
    gateway.set_decision_freshness_policy(
        DecisionFreshnessPolicy(max_age_seconds=30.0, max_future_skew_seconds=2.0)
    )
    return runtime
