from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore
from core.runtime_checkpoint import RuntimeCheckpointStore
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    ATTENTION = "ATTENTION"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RuntimeHealth:
    state: HealthState
    ledger_entries: int
    pending_executions: int
    unknown_executions: int
    recovery_state: RecoveryState
    message: str


class RuntimeHealthMonitor:
    """Read-only observability over persisted runtime safety state."""

    def __init__(
        self,
        *,
        ledger: ExecutionLedger,
        lifecycle: ExecutionLifecycleStore,
        checkpoint_store: RuntimeCheckpointStore,
        recovery: RecoveryCoordinator,
    ) -> None:
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger inválido.")
        if not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle inválido.")
        if not isinstance(checkpoint_store, RuntimeCheckpointStore):
            raise ValueError("checkpoint_store inválido.")
        if not isinstance(recovery, RecoveryCoordinator):
            raise ValueError("recovery inválido.")
        self.ledger = ledger
        self.lifecycle = lifecycle
        self.checkpoint_store = checkpoint_store
        self.recovery = recovery

    def assess(self) -> RuntimeHealth:
        try:
            ledger_entries = len(self.ledger.records())
            records = self.lifecycle.records()
            recovery = self.recovery.assess()
        except ValueError as exc:
            return RuntimeHealth(HealthState.BLOCKED, 0, 0, 0, RecoveryState.INVALID, f"estado inválido: {exc}")

        pending = sum(r.state is ExecutionLifecycleState.PENDING for r in records)
        unknown = sum(r.state is ExecutionLifecycleState.UNKNOWN for r in records)

        if recovery.state is RecoveryState.INVALID or unknown:
            return RuntimeHealth(HealthState.BLOCKED, ledger_entries, pending, unknown, recovery.state, "runtime bloqueado: reconciliação necessária")
        if pending or recovery.state is RecoveryState.REQUIRES_RECONCILIATION:
            return RuntimeHealth(HealthState.ATTENTION, ledger_entries, pending, unknown, recovery.state, "runtime requer verificação antes de retomar")
        return RuntimeHealth(HealthState.HEALTHY, ledger_entries, 0, 0, recovery.state, "runtime sem pendências de segurança")
