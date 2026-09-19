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
    external_id: str | None
    status: ExternalOrderStatus
    message: str
    request_id: str | None = None


@runtime_checkable
class ExternalOrderQueryPort(Protocol):
    def query_order(self, external_id: str) -> ExternalOrderObservation:
        ...

    def query_order_by_request_id(self, request_id: str) -> ExternalOrderObservation:
        ...


@dataclass(frozen=True)
class ReconciliationResult:
    external_id: str | None
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
        if observation.external_id is None:
            raise ValueError("external_id da observação é obrigatório.")
        if not isinstance(observation.external_id, str) or not observation.external_id.strip() or len(observation.external_id.strip()) > 256:
            raise ValueError("external_id da observação inválido.")
        if observation.external_id.strip() != external_id.strip():
            raise ValueError("external_id da observação difere do solicitado.")
        if observation.request_id is not None and (not isinstance(observation.request_id, str) or not observation.request_id.strip() or len(observation.request_id.strip()) > 128):
            raise ValueError("request_id da observação inválido.")
        if not isinstance(observation.status, ExternalOrderStatus):
            raise ValueError("status externo inválido.")
        if not isinstance(observation.message, str) or len(observation.message) > 4096:
            raise ValueError("mensagem da observação inválida.")

        return ReconciliationResult(
            external_id=external_id.strip(),
            status=observation.status,
            reconciled=observation.status in (
                ExternalOrderStatus.EXECUTED,
                ExternalOrderStatus.NOT_EXECUTED,
            ),
            message=observation.message,
        )

    def reconcile_for_request(self, request_id: str, observation: ExternalOrderObservation) -> ReconciliationResult:
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id.strip()) > 128:
            raise ValueError("request_id inválido.")
        if not isinstance(observation, ExternalOrderObservation):
            raise ValueError("observação externa inválida.")
        if observation.request_id != request_id.strip():
            raise ValueError("request_id da observação difere da requisição.")
        if observation.external_id is not None and (not isinstance(observation.external_id, str) or not observation.external_id.strip() or len(observation.external_id.strip()) > 256):
            raise ValueError("external_id da observação inválido.")
        if not isinstance(observation.status, ExternalOrderStatus):
            raise ValueError("status externo inválido.")
        if not isinstance(observation.message, str) or len(observation.message) > 4096:
            raise ValueError("mensagem da observação inválida.")
        return ReconciliationResult(
            external_id=observation.external_id.strip() if observation.external_id else None,
            status=observation.status,
            reconciled=observation.status in (ExternalOrderStatus.EXECUTED, ExternalOrderStatus.NOT_EXECUTED),
            message=observation.message,
        )
