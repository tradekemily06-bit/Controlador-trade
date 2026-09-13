from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.kill_switch import KillSwitch
from core.operation_memory import OperationMemory
from core.p21_observability import RuntimeHealthMonitor
from core.recovery_coordinator import RecoveryCoordinator
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from execution.gateway import ExecutionGateway
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


def build_operational_runtime(root: str | Path) -> OperationalRuntime:
    """Compose one shared runtime; construction has no broker side effects."""
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
    gateway = ExecutionGateway(
        PaperExecutor(),
        kill_switch,
        ledger=ledger,
        lifecycle=lifecycle,
    )
    return OperationalRuntime(
        kill_switch=kill_switch,
        execution_ledger=ledger,
        execution_lifecycle=lifecycle,
        checkpoint_store=checkpoint,
        recovery=recovery,
        health=health,
        gateway=gateway,
    )
