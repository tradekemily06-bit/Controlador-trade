from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore


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
    message: str


class RuntimeHealthMonitor:
    """Read-only runtime health monitor; it never executes or mutates trading state."""

    def __init__(self, *, ledger: ExecutionLedger, lifecycle: ExecutionLifecycleStore) -> None:
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger inválido.")
        if not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle inválido.")
        self.ledger = ledger
        self.lifecycle = lifecycle

    def assess(self) -> RuntimeHealth:
        try:
            ledger_entries = len(self.ledger.records())
            records = self.lifecycle.records()
        except ValueError as exc:
            return RuntimeHealth(HealthState.BLOCKED, 0, 0, 0, f"estado inválido: {exc}")
        pending = sum(r.state is ExecutionLifecycleState.PENDING for r in records)
        unknown = sum(r.state is ExecutionLifecycleState.UNKNOWN for r in records)
        if unknown:
            return RuntimeHealth(HealthState.BLOCKED, ledger_entries, pending, unknown, "execuções UNKNOWN requerem reconciliação")
        if pending:
            return RuntimeHealth(HealthState.ATTENTION, ledger_entries, pending, 0, "existem execuções PENDING para verificação")
        return RuntimeHealth(HealthState.HEALTHY, ledger_entries, 0, 0, "runtime sem pendências")
