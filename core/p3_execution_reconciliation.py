from __future__ import annotations

from datetime import datetime, timezone

from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
    ReconciliationResult,
)
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import (
    ExecutionLifecycleRecord,
    ExecutionLifecycleState,
    ExecutionLifecycleStore,
)


class ExecutionReconciliationCoordinator:
    """Apply a verified external observation to durable execution authorities.

    This coordinator never submits an order. It only moves already-reserved/
    uncertain state to an externally confirmed terminal state. Cross-store
    writes are deliberately retryable: if one store fails, recovery remains
    blocked and a later identical reconciliation can safely finish the pair.
    """

    def __init__(self, *, ledger: ExecutionLedger, lifecycle: ExecutionLifecycleStore) -> None:
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger inválido.")
        if not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle inválido.")
        self._ledger = ledger
        self._lifecycle = lifecycle
        self._boundary = ExternalOrderReconciliationBoundary()

    @staticmethod
    def _target(status: ExternalOrderStatus) -> tuple[bool, ExecutionLedgerStatus, ExecutionLifecycleState] | None:
        if status is ExternalOrderStatus.EXECUTED:
            return True, ExecutionLedgerStatus.RECONCILED_EXECUTED, ExecutionLifecycleState.ACCEPTED
        if status is ExternalOrderStatus.NOT_EXECUTED:
            return False, ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED, ExecutionLifecycleState.REJECTED
        return None

    def reconcile(
        self,
        request_id: str,
        external_id: str,
        observation: ExternalOrderObservation,
        *,
        updated_at: datetime | None = None,
    ) -> ReconciliationResult:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        result = self._boundary.reconcile(external_id, observation)
        target = self._target(result.status)
        if target is None:
            return result

        executed, ledger_target, lifecycle_target = target
        timestamp = updated_at or datetime.now(timezone.utc)
        if not isinstance(timestamp, datetime):
            raise ValueError("updated_at inválido.")

        ledger_state = self._ledger.status(request_id)
        lifecycle_record = self._lifecycle.get(request_id)
        lifecycle_state = lifecycle_record.state if lifecycle_record is not None else None

        if ledger_state is None and lifecycle_record is None:
            raise ValueError("request_id não existe nas autoridades duráveis.")

        # Never manufacture a REAL ACCEPTED ledger entry from an orphan
        # lifecycle record. A missing reservation has no proof that this
        # request was admitted by the execution boundary.
        if ledger_state is None:
            raise ValueError("ledger ausente; reconciliação segura não pode criar autorização REAL retroativa.")

        compatible_ledger = {
            ExecutionLedgerStatus.RESERVED,
            ExecutionLedgerStatus.UNKNOWN,
            ledger_target,
        }
        if ledger_state not in compatible_ledger:
            raise ValueError("observação externa não é compatível com o estado terminal do ledger.")

        compatible_lifecycle = {
            None,
            ExecutionLifecycleState.PENDING,
            ExecutionLifecycleState.UNKNOWN,
            lifecycle_target,
        }
        if lifecycle_state not in compatible_lifecycle:
            raise ValueError("observação externa não é compatível com o estado terminal do lifecycle.")

        # Apply only idempotent, explicitly reconciled transitions.
        if ledger_state in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
            self._ledger.reconcile(request_id, executed=executed)

        lifecycle_record = self._lifecycle.get(request_id)
        if lifecycle_record is None:
            self._lifecycle.put(
                ExecutionLifecycleRecord(
                    request_id,
                    lifecycle_target,
                    timestamp,
                    f"reconciliado externamente: {result.message}",
                )
            )
        elif lifecycle_record.state in (ExecutionLifecycleState.PENDING, ExecutionLifecycleState.UNKNOWN):
            self._lifecycle.reconcile(
                request_id,
                lifecycle_target,
                updated_at=timestamp,
                message=f"reconciliado externamente: {result.message}",
            )

        return result
