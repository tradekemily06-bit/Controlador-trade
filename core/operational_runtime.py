from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.kill_switch import KillSwitch
from core.operational_state import OperationalState
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from core.operation_memory import OperationMemory
from core.daily_operation_journal import DailyOperationJournal
from core.p21_observability import RuntimeHealthMonitor
from core.recovery_coordinator import RecoveryCoordinator
from core.risk_manager import RiskManager
from core.runtime_checkpoint import RuntimeCheckpointStore
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from execution.gateway import ExecutionGateway
from integration.market_data_execution_guard import MarketDataExecutionGuard
from execution.ports import ExecutionPort
from execution.paper import PaperExecutor
from typing import Callable


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
    market_data: MarketDataRuntimeState
    market_data_execution_guard: MarketDataExecutionGuard
    daily_journal: DailyOperationJournal
    risk_state_provider: Callable[[], OperationalState] | None
    risk_manager: RiskManager


def build_operational_runtime(root: str | Path, executor: ExecutionPort | None = None, risk_state_provider: Callable[[], OperationalState] | None = None, kill_switch: KillSwitch | None = None) -> OperationalRuntime:
    """Compose one shared runtime; broker selection is injected at the edge."""
    root = Path(root)
    kill_switch = kill_switch or KillSwitch()
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
    selected_executor = executor or PaperExecutor()
    market_data = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    daily_journal = DailyOperationJournal(root / "daily-operation-journal.json")
    provider = risk_state_provider or getattr(selected_executor, "read_operational_state", None)
    risk_manager = RiskManager()
    gateway = ExecutionGateway(
        selected_executor,
        kill_switch,
        ledger=ledger,
        lifecycle=lifecycle,
        risk_check=lambda: risk_manager.evaluate(state=provider() if callable(provider) else None),
    )
    market_data_execution_guard = MarketDataExecutionGuard(market_data=market_data, gateway=gateway)
    return OperationalRuntime(
        kill_switch=kill_switch,
        execution_ledger=ledger,
        execution_lifecycle=lifecycle,
        checkpoint_store=checkpoint,
        recovery=recovery,
        health=health,
        gateway=gateway,
        market_data=market_data,
        market_data_execution_guard=market_data_execution_guard,
        daily_journal=daily_journal,
        risk_state_provider=provider if callable(provider) else None,
        risk_manager=risk_manager,
    )
