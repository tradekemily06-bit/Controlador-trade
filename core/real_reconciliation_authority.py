from __future__ import annotations

from typing import Protocol

from core.p121_external_order_reconciliation import (
    ExternalOrderQueryPort,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)


class ReconciliationEvidenceAuthority(Protocol):
    """Authoritative read-only verifier for REAL reconciliation evidence."""

    def verify(self, *, request_id: str, evidence_id: str, evidence_source: str, executed: bool) -> bool:
        ...


class BrokerReconciliationEvidenceAuthority:
    """Verify evidence against the broker's read-only external-order query port.

    Evidence is bound to the request that produced it and to the configured
    evidence source. A matching external id alone is never sufficient: an
    evidence record for another request must not reconcile this request.
    """

    def __init__(self, query_port: ExternalOrderQueryPort, *, evidence_source: str) -> None:
        if query_port is None or not callable(getattr(query_port, "query_order", None)):
            raise ValueError("query_port de reconciliação é obrigatório.")
        if not isinstance(evidence_source, str) or not evidence_source.strip():
            raise ValueError("evidence_source autoritativo é obrigatório.")
        self._query_port = query_port
        self._evidence_source = evidence_source.strip()
        self._boundary = ExternalOrderReconciliationBoundary()

    def verify(self, *, request_id: str, evidence_id: str, evidence_source: str, executed: bool) -> bool:
        if not isinstance(request_id, str) or not request_id.strip():
            return False
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            return False
        if not isinstance(evidence_source, str) or not evidence_source.strip():
            return False
        if evidence_source.strip() != self._evidence_source:
            return False
        try:
            observation = self._query_port.query_order(evidence_id.strip())
            result = self._boundary.reconcile(evidence_id.strip(), observation)
        except Exception:
            return False
        if not result.reconciled:
            return False
        # The external broker observation must carry the originating request
        # identity and source. Missing metadata is deliberately fail-closed.
        if observation.request_id != request_id.strip():
            return False
        if observation.evidence_source != self._evidence_source:
            return False
        expected = ExternalOrderStatus.EXECUTED if executed else ExternalOrderStatus.NOT_EXECUTED
        return result.status is expected
