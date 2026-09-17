from __future__ import annotations

import pytest

from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)


def _observation(status: ExternalOrderStatus) -> ExternalOrderObservation:
    return ExternalOrderObservation(
        external_id="ext-stage7-1",
        status=status,
        message="synthetic reconciliation exercise",
        request_id="req-stage7-1",
        evidence_source="test://stage7-reconciliation-exercise",
        broker_id="demo-broker",
        symbol="EURUSD",
    )


def test_unknown_external_state_remains_unreconciled():
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-stage7-1", _observation(ExternalOrderStatus.UNKNOWN)
    )
    assert result.reconciled is False
    assert result.status is ExternalOrderStatus.UNKNOWN


def test_executed_external_state_is_reconciled_with_bound_identity():
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-stage7-1", _observation(ExternalOrderStatus.EXECUTED)
    )
    assert result.reconciled is True
    assert result.status is ExternalOrderStatus.EXECUTED


def test_reconciliation_rejects_missing_identity_evidence():
    observation = _observation(ExternalOrderStatus.EXECUTED)
    observation = ExternalOrderObservation(
        external_id=observation.external_id,
        status=observation.status,
        message=observation.message,
        request_id=None,
        evidence_source=observation.evidence_source,
        broker_id=observation.broker_id,
        symbol=observation.symbol,
    )
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile("ext-stage7-1", observation)
