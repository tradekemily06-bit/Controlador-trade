from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


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
