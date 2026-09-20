from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


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
    # Optional for external-id queries; mandatory and correlated by the
    # request-id recovery path. Keeping it optional preserves the existing
    # external-id query contract while allowing recovery to prove that the
    # broker observation belongs to the requested client-order reference.
    request_id: str | None = None


@runtime_checkable
class ExternalOrderQueryPort(Protocol):
    """Read-only broker query port used as the source of reconciliation evidence."""

    def query_order(self, external_id: str) -> ExternalOrderObservation:
        ...


@runtime_checkable
class ExternalOrderRequestQueryPort(Protocol):
    """Read-only broker lookup by the durable client-order/request reference.

    This is the recovery path for the crash window where the broker accepted
    the order but the local Ledger has not yet persisted external_id.
    Implementations must map the request reference to the broker's native
    client-order-id/idempotency field; callers never supply an arbitrary
    broker order identifier here.
    """

    def query_order_by_request_id(self, request_id: str) -> ExternalOrderObservation:
        ...


@dataclass(frozen=True)
class ReconciliationResult:
    external_id: str
    status: ExternalOrderStatus
    reconciled: bool
    message: str


class ExternalOrderReconciliationBoundary:
    """Turns a broker query response into reconciliation evidence.

    A caller cannot close a REAL request by supplying a local boolean or a
    hand-built observation. The boundary must query the broker-side port.
    """

    def reconcile(
        self,
        external_id: str,
        *,
        query_port: ExternalOrderQueryPort,
    ) -> ReconciliationResult:
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido.")
        if not isinstance(query_port, ExternalOrderQueryPort):
            raise ValueError("query_port de reconciliação inválido.")

        requested_id = external_id.strip()
        observation = query_port.query_order(requested_id)

        if not isinstance(observation, ExternalOrderObservation):
            raise ValueError("observação externa inválida.")
        if not isinstance(observation.external_id, str) or not observation.external_id.strip():
            raise ValueError("external_id observado inválido.")
        if not isinstance(observation.message, str):
            raise ValueError("mensagem externa inválida.")
        observed_id = observation.external_id.strip()
        if observed_id != requested_id:
            raise ValueError("external_id retornado pelo broker difere do solicitado.")
        if not isinstance(observation.status, ExternalOrderStatus):
            raise ValueError("status externo inválido.")

        return ReconciliationResult(
            external_id=requested_id,
            status=observation.status,
            reconciled=observation.status
            in (
                ExternalOrderStatus.EXECUTED,
                ExternalOrderStatus.NOT_EXECUTED,
            ),
            message=observation.message,
        )
