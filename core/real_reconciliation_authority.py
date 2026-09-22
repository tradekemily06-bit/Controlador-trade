from __future__ import annotations

from typing import Protocol

from core.p121_external_order_reconciliation import (
    ExternalOrderQueryPort,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)


class ReconciliationEvidenceAuthority(Protocol):
    """Authoritative read-only verifier for REAL reconciliation evidence."""

    def verify(
        self,
        *,
        request_id: str,
        evidence_id: str,
        evidence_source: str,
        broker_id: str,
        symbol: str,
        executed: bool,
    ) -> bool:
        ...


class BrokerReconciliationEvidenceAuthority:
    """Verify broker evidence against the immutable REAL operation identity."""

    def __init__(self, query_port: ExternalOrderQueryPort, *, evidence_source: str) -> None:
        if query_port is None or not callable(getattr(query_port, "query_order", None)):
            raise ValueError("query_port de reconciliação é obrigatório.")
        if not isinstance(evidence_source, str) or not evidence_source.strip():
            raise ValueError("evidence_source autoritativo é obrigatório.")
        self._query_port = query_port
        self._evidence_source = evidence_source.strip()
        self._boundary = ExternalOrderReconciliationBoundary()

    def verify(
        self,
        *,
        request_id: str,
        evidence_id: str,
        evidence_source: str,
        broker_id: str,
        symbol: str,
        executed: bool,
    ) -> bool:
        values = (request_id, evidence_id, evidence_source, broker_id, symbol)
        if not isinstance(executed, bool):
            return False
        if any(not isinstance(value, str) or not value.strip() for value in values):
            return False
        request_id = request_id.strip()
        evidence_id = evidence_id.strip()
        evidence_source = evidence_source.strip()
        broker_id = broker_id.strip().lower()
        symbol = symbol.strip().upper()
        if evidence_source != self._evidence_source:
            return False
        try:
            observation = self._query_port.query_order(evidence_id)
            result = self._boundary.reconcile(evidence_id, observation)
        except Exception:
            return False
        if not result.reconciled:
            return False
        # Broker observations are untrusted external input. Every identity field
        # must be present and type-valid before normalization; never call .strip()
        # on optional metadata directly.
        observation_values = (
            observation.request_id,
            observation.evidence_source,
            observation.broker_id,
            observation.symbol,
        )
        if any(not isinstance(value, str) or not value.strip() for value in observation_values):
            return False
        if observation.request_id.strip() != request_id:
            return False
        if observation.evidence_source.strip() != self._evidence_source:
            return False
        if observation.broker_id.strip().lower() != broker_id:
            return False
        if observation.symbol.strip().upper() != symbol:
            return False
        expected = ExternalOrderStatus.EXECUTED if executed else ExternalOrderStatus.NOT_EXECUTED
        return result.status is expected
