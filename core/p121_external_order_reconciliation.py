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
    # These fields are mandatory for REAL reconciliation authority even though
    # they have defaults for source compatibility with older observations.
    request_id: str | None = None
    evidence_source: str | None = None


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
        if not isinstance(observation.request_id, str) or not observation.request_id.strip():
            raise ValueError("request_id da observação externa é obrigatório para reconciliação REAL.")
        if not isinstance(observation.evidence_source, str) or not observation.evidence_source.strip():
            raise ValueError("evidence_source da observação externa é obrigatório para reconciliação REAL.")

        return ReconciliationResult(
            external_id=external_id.strip(),
            status=observation.status,
            reconciled=observation.status in (
                ExternalOrderStatus.EXECUTED,
                ExternalOrderStatus.NOT_EXECUTED,
            ),
            message=observation.message,
        )
