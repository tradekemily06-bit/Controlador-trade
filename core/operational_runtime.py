from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.kill_switch import KillSwitch
from core.operation_lineage import OperationLineageStore
from core.controlled_automation_runtime import ControlledAutomationRuntime
from core.p41_controlled_automation import AutomationPolicy
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from core.operation_memory import OperationMemory
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
    execution_ledger: ExecutionLedger
    execution_lifecycle: ExecutionLifecycleStore
    checkpoint_store: RuntimeCheckpointStore
    recovery: RecoveryCoordinator
    health: RuntimeHealthMonitor
    gateway: ExecutionGateway
    lineage: OperationLineageStore
    market_data: MarketDataRuntimeState
    controlled_automation: ControlledAutomationRuntime


def build_operational_runtime(root: str | Path, executor: ExecutionPort | None = None) -> OperationalRuntime:
    """Compose one shared runtime; broker selection is injected at the edge."""
    root = Path(root)
    kill_switch = KillSwitch()
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
    lineage = OperationLineageStore(root / "operation-lineage.json")
    gateway = ExecutionGateway(
        executor or PaperExecutor(),
        kill_switch,
        ledger=ledger,
        lifecycle=lifecycle,
        lineage=lineage,
    )
    market_data = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    # Automation is explicitly opt-in; the shared runtime starts fail-closed.
    controlled_automation = ControlledAutomationRuntime(
        policy=AutomationPolicy(enabled=False, minimum_interval_seconds=0)
    )
    return OperationalRuntime(
        kill_switch=kill_switch,
        execution_ledger=ledger,
        execution_lifecycle=lifecycle,
        checkpoint_store=checkpoint,
        recovery=recovery,
        health=health,
        gateway=gateway,
        lineage=lineage,
        market_data=market_data,
        controlled_automation=controlled_automation,
    )
