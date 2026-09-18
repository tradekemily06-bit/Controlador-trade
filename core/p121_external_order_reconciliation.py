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
    request_id: str | None = None
    evidence_source: str | None = None
    broker_id: str | None = None
    symbol: str | None = None


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

    def reconcile(
        self,
        external_id: str,
        observation: ExternalOrderObservation,
        *,
        expected_request_id: str | None = None,
        expected_broker_id: str | None = None,
        expected_symbol: str | None = None,
    ) -> ReconciliationResult:
        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("external_id inválido.")
        if not isinstance(observation, ExternalOrderObservation):
            raise ValueError("observação externa inválida.")
        if observation.external_id.strip() != external_id.strip():
            raise ValueError("external_id da observação difere do solicitado.")
        for name, expected, actual in (
            ("request_id", expected_request_id, observation.request_id),
            ("broker_id", expected_broker_id, observation.broker_id),
            ("symbol", expected_symbol, observation.symbol),
        ):
            if expected is not None and (not isinstance(expected, str) or not expected.strip()):
                raise ValueError(f"{name} esperado inválido.")
            if expected is not None and actual.strip() != expected.strip():
                raise ValueError(f"{name} da observação difere do contexto esperado.")
        if not isinstance(observation.status, ExternalOrderStatus):
            raise ValueError("status externo inválido.")
        if not isinstance(observation.request_id, str) or not observation.request_id.strip():
            raise ValueError("request_id da observação externa é obrigatório para reconciliação REAL.")
        if not isinstance(observation.evidence_source, str) or not observation.evidence_source.strip():
            raise ValueError("evidence_source da observação externa é obrigatório para reconciliação REAL.")
        if not isinstance(observation.broker_id, str) or not observation.broker_id.strip():
            raise ValueError("broker_id da observação externa é obrigatório para reconciliação REAL.")
        if not isinstance(observation.symbol, str) or not observation.symbol.strip():
            raise ValueError("symbol da observação externa é obrigatório para reconciliação REAL.")
        if not isinstance(observation.message, str) or not observation.message.strip():
            raise ValueError("message da observação externa é obrigatória.")

        return ReconciliationResult(
            external_id=external_id.strip(),
            status=observation.status,
            reconciled=observation.status in (ExternalOrderStatus.EXECUTED, ExternalOrderStatus.NOT_EXECUTED),
            message=observation.message,
        )
