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

    def request_execution_lock(self, request_id: str):
        """Serialize identity discovery with REAL dispatch for one request."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        return self._ledger.request_execution_lock(request_id)

    def external_id_for(self, request_id: str) -> str | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        return self._ledger.external_id(request_id)

    def _bind_external_id_locked(self, request_id: str, external_id: str) -> None:
        """Bind an external identity while the caller already holds the request lock."""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido.")
        status = self._ledger.status(request_id)
        if status is None:
            raise ValueError("request_id não existe nas autoridades duráveis.")
        self._ledger.bind_external_id(request_id, external_id.strip())

    def bind_external_id(self, request_id: str, external_id: str) -> None:
        """Durably bind a broker identity under the same lock used by REAL dispatch."""
        with self.request_execution_lock(request_id):
            self._bind_external_id_locked(request_id, external_id)

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

        # A RESERVED/UNKNOWN request can only be reconciled against the exact
        # broker/exchange identity durably bound to that request. Without that
        # binding there is no safe proof that an arbitrary external order is
        # the order created by this request_id.
        bound_external_id = self._ledger.external_id(request_id)
        if ledger_state in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
            if bound_external_id is None:
                raise ValueError(
                    "request_id incerto sem external_id durável; reconciliação externa segura indisponível."
                )
            if bound_external_id != result.external_id:
                raise ValueError(
                    "external_id informado difere da identidade externa durável do request_id."
                )
        elif bound_external_id is None:
            # Legacy terminal entries may be repaired internally from the
            # ledger, but external evidence is identity-sensitive. Without a
            # durable binding we cannot prove that this broker observation
            # belongs to this request.
            raise ValueError(
                "estado terminal sem external_id durável; observação externa não é compatível com uma reconciliação segura."
            )
        elif bound_external_id != result.external_id:
            # For already-terminal ledger records, the external identity is
            # still authoritative when present. This prevents closing a
            # lifecycle projection using evidence belonging to another order.
            raise ValueError(
                "external_id informado difere da identidade externa durável do request_id."
            )

        # A terminal ledger state is already durable proof. When the
        # lifecycle projection is missing, external evidence may only complete
        # the projection if it agrees with that terminal outcome. It must never
        # be allowed to reverse an accepted/rejected execution.
        compatible_ledger = {
            ExecutionLedgerStatus.RESERVED,
            ExecutionLedgerStatus.UNKNOWN,
            ledger_target,
        }
        if ledger_state in (
            ExecutionLedgerStatus.ACCEPTED,
            ExecutionLedgerStatus.RECONCILED_EXECUTED,
        ):
            if ledger_target is not ExecutionLedgerStatus.RECONCILED_EXECUTED:
                raise ValueError("observação externa não é compatível com o estado terminal do ledger.")
        elif ledger_state in (
            ExecutionLedgerStatus.REJECTED,
            ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
        ):
            if ledger_target is not ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED:
                raise ValueError("observação externa não é compatível com o estado terminal do ledger.")
        elif ledger_state not in compatible_ledger:
            raise ValueError("observação externa não é compatível com o estado terminal do ledger.")

        compatible_lifecycle = {
            None,
            ExecutionLifecycleState.PENDING,
            ExecutionLifecycleState.UNKNOWN,
            lifecycle_target,
        }
        if lifecycle_state not in compatible_lifecycle:
            raise ValueError("observação externa não é compatível com o estado terminal do lifecycle.")

        # Serialize reconciliation against the REAL dispatch side effect for
        # this request. Without this lock, a worker could read an external
        # observation and change RESERVED -> terminal between the gateway final
        # authority check and the broker call (a TOCTOU race).
        with self._ledger.request_execution_lock(request_id):
            ledger_state = self._ledger.status(request_id)
            lifecycle_record = self._lifecycle.get(request_id)
            lifecycle_state = lifecycle_record.state if lifecycle_record is not None else None
            bound_external_id = self._ledger.external_id(request_id)

            # Re-evaluate the observation against the authoritative state after
            # acquiring the same lock used by REAL dispatch. The pre-lock
            # validation is only an admission snapshot: execution may have
            # completed while reconciliation was waiting. A stale observation
            # must never be reported as successfully applied to a terminal
            # request, especially when it contradicts the terminal outcome.
            if bound_external_id is not None and bound_external_id != result.external_id:
                raise ValueError(
                    "external_id durável divergiu durante a reconciliação concorrente."
                )
            if ledger_state in (
                ExecutionLedgerStatus.ACCEPTED,
                ExecutionLedgerStatus.RECONCILED_EXECUTED,
            ):
                if ledger_target is not ExecutionLedgerStatus.RECONCILED_EXECUTED:
                    raise ValueError(
                        "observação externa diverge do resultado terminal já confirmado no ledger."
                    )
            elif ledger_state in (
                ExecutionLedgerStatus.REJECTED,
                ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
            ):
                if ledger_target is not ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED:
                    raise ValueError(
                        "observação externa diverge do resultado terminal já confirmado no ledger."
                    )
            elif ledger_state is None:
                raise ValueError("ledger ausente durante a reconciliação concorrente.")

            if ledger_state in (ExecutionLedgerStatus.RESERVED, ExecutionLedgerStatus.UNKNOWN):
                try:
                    self._ledger.reconcile(request_id, executed=executed)
                except ValueError:
                    raced_state = self._ledger.status(request_id)
                    if raced_state is not ledger_target:
                        raise
                    raced_external_id = self._ledger.external_id(request_id)
                    if raced_external_id != result.external_id:
                        raise ValueError(
                            "external_id durável mudou ou divergiu durante a reconciliação concorrente."
                        )

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
                try:
                    self._lifecycle.reconcile(
                        request_id,
                        lifecycle_target,
                        updated_at=timestamp,
                        message=f"reconciliado externamente: {result.message}",
                    )
                except ValueError:
                    raced_lifecycle = self._lifecycle.get(request_id)
                    if raced_lifecycle is None or raced_lifecycle.state is not lifecycle_target:
                        raise

        return result
