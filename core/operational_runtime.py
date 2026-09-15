from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.decision_audit import DecisionAudit
from core.ecosystem_maintenance import MaintenanceManager
from core.kill_switch import KillSwitch
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from core.operation_memory import OperationMemory
from core.operational_safety_store import OperationalSafetyStore
from core.p21_observability import RuntimeHealthMonitor
from core.recovery_coordinator import RecoveryCoordinator
from core.runtime_checkpoint import RuntimeCheckpointStore
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
    execution_ledger: ExecutionLedger
    execution_lifecycle: ExecutionLifecycleStore
    checkpoint_store: RuntimeCheckpointStore
    recovery: RecoveryCoordinator
    health: RuntimeHealthMonitor
    gateway: ExecutionGateway
    market_data: MarketDataRuntimeState
    safety_store: OperationalSafetyStore
    safety_audit: DecisionAudit


def build_operational_runtime(root: str | Path, executor: ExecutionPort | None = None) -> OperationalRuntime:
    """Compose one shared runtime with fail-closed durable safety state."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    safety_store = OperationalSafetyStore(root / "operational-safety.json")
    try:
        safety_audit, persisted_switch = safety_store.load()
        initial_enabled = persisted_switch.state.enabled
        initial_reason = persisted_switch.state.reason
        safety_state_valid = True
    except (OSError, ValueError, TypeError) as exc:
        safety_audit = DecisionAudit()
        initial_enabled = True
        initial_reason = f"estado de segurança indisponível: {type(exc).__name__}"
        safety_state_valid = False

    # Persist only after the KillSwitch has been constructed. A corrupt or
    # unavailable prior state is replaced by a minimal, valid fail-closed
    # state rather than recursively reading the corrupt payload during startup.
    kill_switch: KillSwitch

    def persist_safety(_state) -> None:
        safety_store.save(safety_audit, kill_switch)

    kill_switch = KillSwitch(on_change=persist_safety)
    if initial_enabled:
        kill_switch.activate(initial_reason or "estado de segurança persistido")
    elif safety_state_valid:
        safety_store.save(safety_audit, kill_switch)

    maintenance = MaintenanceManager(root / "maintenance.json")
    ledger = ExecutionLedger(root / "execution-ledger.json")
    lifecycle = ExecutionLifecycleStore(root / "execution-lifecycle.json")
    checkpoint = RuntimeCheckpointStore(root / "runtime-checkpoint.json")
    memory = OperationMemory()
    recovery = RecoveryCoordinator(
        checkpoint_store=checkpoint,
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=memory,
    )
    health = RuntimeHealthMonitor(
        ledger=ledger,
        lifecycle=lifecycle,
        checkpoint_store=checkpoint,
        recovery=recovery,
    )
    gateway = ExecutionGateway(
        executor or PaperExecutor(),
        kill_switch,
        ledger=ledger,
        lifecycle=lifecycle,
        maintenance=maintenance,
    )
    market_data = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    return OperationalRuntime(
        kill_switch=kill_switch,
        maintenance=maintenance,
        execution_ledger=ledger,
        execution_lifecycle=lifecycle,
        checkpoint_store=checkpoint,
        recovery=recovery,
        health=health,
        gateway=gateway,
        market_data=market_data,
        safety_store=safety_store,
        safety_audit=safety_audit,
    )
