from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.operation_lineage import OperationLineageStore
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderQueryPort, ExternalOrderStatus, ReconciliationResult, ExternalOrderReconciliationBoundary
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore


@dataclass(frozen=True)
class ExternalReconciliationRun:
    request_id: str
    external_id: str
    observation: ExternalOrderObservation
    result: ReconciliationResult
    ledger_updated: bool
    lifecycle_updated: bool


class ExternalReconciliationCoordinator:
    """Queries an external reference and reconciles only uncertain local state."""

    def __init__(
        self,
        *,
        query: ExternalOrderQueryPort,
        lineage: OperationLineageStore,
        ledger: ExecutionLedger,
        lifecycle: ExecutionLifecycleStore,
    ) -> None:
        self.query = query
        self.lineage = lineage
        self.ledger = ledger
        self.lifecycle = lifecycle

    def reconcile_request(self, request_id: str, *, now: datetime | None = None) -> ExternalReconciliationRun:
        lineage = self.lineage.get(request_id)
        if lineage is None:
            raise ValueError("request_id sem linhagem persistida.")
        if not lineage.external_id:
            raise ValueError("request_id sem external_id para reconciliação.")

        observation = self.query.query_order(lineage.external_id)
        result = ExternalOrderReconciliationBoundary().reconcile(lineage.external_id, observation)
        event_time = now or datetime.now(timezone.utc)
        ledger_updated = False
        lifecycle_updated = False

        if result.status in (ExternalOrderStatus.EXECUTED, ExternalOrderStatus.NOT_EXECUTED):
            ledger_state = self.ledger.status(request_id)
            if ledger_state in (ExecutionLedgerStatus.UNKNOWN, ExecutionLedgerStatus.RESERVED):
                self.ledger.reconcile(request_id, executed=result.status is ExternalOrderStatus.EXECUTED)
                ledger_updated = True

            lifecycle_state = self.lifecycle.get(request_id)
            if lifecycle_state is not None and lifecycle_state.state is ExecutionLifecycleState.UNKNOWN:
                target = ExecutionLifecycleState.ACCEPTED if result.status is ExternalOrderStatus.EXECUTED else ExecutionLifecycleState.REJECTED
                self.lifecycle.reconcile(request_id, target, updated_at=event_time, message=result.message)
                lifecycle_updated = True

        return ExternalReconciliationRun(
            request_id=request_id,
            external_id=lineage.external_id,
            observation=observation,
            result=result,
            ledger_updated=ledger_updated,
            lifecycle_updated=lifecycle_updated,
        )
