from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.kill_switch import KillSwitch
from core.operational_state import OperationalState
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from core.operational_safety_store import OperationalSafetyStore
from core.daily_operation_journal import DailyOperationJournal
from core.demo_autonomy_authorization import DemoAutonomyAuthorizationStore
from core.p21_observability import RuntimeHealthMonitor
from core.recovery_coordinator import RecoveryCoordinator
from core.risk_manager import RiskManager
from core.runtime_checkpoint import RuntimeCheckpoint, RuntimeCheckpointStore
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
    session_id: str
    safety_store: OperationalSafetyStore
    demo_autonomy: DemoAutonomyAuthorizationStore

    def activate_kill_switch(self, reason: str) -> None:
        """Activate and durably persist the shared kill switch."""
        self.kill_switch.activate(reason)
        self.safety_store.save_kill_switch_state(self.kill_switch)

    def checkpoint_operation(self, request_id: str) -> bool:
        """Persist the last terminal operation without authorizing or replaying it."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido para checkpoint")
        previous = self.checkpoint_store.load()
        next_cycle = (previous.last_cycle + 1) if previous is not None else 1
        self.checkpoint_store.save(
            RuntimeCheckpoint(
                session_id=self.session_id,
                last_cycle=next_cycle,
                last_request_id=request_id.strip(),
                updated_at=datetime.now(timezone.utc),
            )
        )
        return True


def build_operational_runtime(root: str | Path, executor: ExecutionPort | None = None, risk_state_provider: Callable[[], OperationalState] | None = None, kill_switch: KillSwitch | None = None) -> OperationalRuntime:
    """Compose one shared runtime; broker selection is injected at the edge."""
    root = Path(root)
    safety_store = OperationalSafetyStore(root / "operational-safety.json")
    demo_autonomy = DemoAutonomyAuthorizationStore(root / "demo-autonomy.json")
    persisted_kill_switch = KillSwitch()
    try:
        _, persisted_kill_switch = safety_store.load()
    except ValueError:
        persisted_kill_switch.activate("estado de segurança persistido inválido")
    kill_switch = kill_switch or persisted_kill_switch
    if persisted_kill_switch.state.enabled and not kill_switch.state.enabled:
        kill_switch.activate(persisted_kill_switch.state.reason or "estado persistido")
    ledger = ExecutionLedger(root / "execution-ledger.json")
    lifecycle = ExecutionLifecycleStore(root / "execution-lifecycle.json")
    checkpoint = RuntimeCheckpointStore(root / "runtime-checkpoint.json")
    previous_checkpoint = checkpoint.load()
    session_id = uuid4().hex
    if previous_checkpoint is not None and session_id == previous_checkpoint.session_id:
        session_id = f"{session_id}-{datetime.now(timezone.utc).timestamp_ns()}"
    recovery = RecoveryCoordinator(
        checkpoint_store=checkpoint,
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
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
        session_id=session_id,
        safety_store=safety_store,
        demo_autonomy=demo_autonomy,
    )
