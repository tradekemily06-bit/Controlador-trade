from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore


class ExternalOrderStatus(str, Enum):
    EXECUTED = "EXECUTED"
    NOT_EXECUTED = "NOT_EXECUTED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExternalOrderObservation:
    external_id: str
    status: ExternalOrderStatus
    message: str


class ExternalOrderQueryPort(Protocol):
    def query_order(self, external_id: str) -> ExternalOrderObservation:
        ...


@dataclass(frozen=True)
class ReconciliationResult:
    external_id: str
    status: ExternalOrderStatus
    reconciled: bool
    message: str


class ExternalOrderReconciliationBoundary:
    """Read-only external order reconciliation; it never resubmits an order."""

    def reconcile(self, external_id: str, observation: ExternalOrderObservation) -> ReconciliationResult:
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido.")
        if not isinstance(observation, ExternalOrderObservation):
            raise ValueError("observação externa inválida.")
        if observation.external_id.strip() != external_id.strip():
            raise ValueError("external_id da observação difere do solicitado.")
        if not isinstance(observation.status, ExternalOrderStatus):
            raise ValueError("status externo inválido.")

        return ReconciliationResult(
            external_id=external_id.strip(),
            status=observation.status,
            reconciled=observation.status in (
                ExternalOrderStatus.EXECUTED,
                ExternalOrderStatus.NOT_EXECUTED,
            ),
            message=observation.message,
        )


    def reconcile_request(
        self,
        *,
        request_id: str,
        ledger: ExecutionLedger,
        lifecycle: ExecutionLifecycleStore,
        query_port: ExternalOrderQueryPort,
    ) -> ReconciliationResult:
        """Query the broker by the durable external ID and project a terminal result. This is fail-closed if either durable store update fails.

        This path is read-only toward the broker: it never resubmits an order.
        """
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id inválido.")
        if not isinstance(ledger, ExecutionLedger):
            raise ValueError("ledger inválido.")
        if not isinstance(lifecycle, ExecutionLifecycleStore):
            raise ValueError("lifecycle inválido.")
        external_id = ledger.external_id(request_id)
        if external_id is None:
            raise ValueError("request_id não possui external_id durável para reconciliação.")
        observation = query_port.query_order(external_id)
        result = self.reconcile(external_id, observation)
        if result.status is ExternalOrderStatus.EXECUTED:
            ledger.reconcile(request_id, executed=True, external_id=external_id)
            lifecycle.reconcile(
                request_id,
                ExecutionLifecycleState.ACCEPTED,
                updated_at=datetime.now(timezone.utc),
                message=result.message,
            )
        elif result.status is ExternalOrderStatus.NOT_EXECUTED:
            ledger.reconcile(request_id, executed=False, external_id=external_id)
            lifecycle.reconcile(
                request_id,
                ExecutionLifecycleState.REJECTED,
                updated_at=datetime.now(timezone.utc),
                message=result.message,
            )
        return result
