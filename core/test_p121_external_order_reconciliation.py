import pytest

from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)


def observation(external_id="ext-1", status=ExternalOrderStatus.EXECUTED, request_id="req-1", source="broker", broker="broker", symbol="EURUSD"):
    return ExternalOrderObservation(external_id, status, "filled", request_id=request_id, evidence_source=source, broker_id=broker, symbol=symbol)


def test_terminal_external_status_reconciles():
    result = ExternalOrderReconciliationBoundary().reconcile("ext-1", observation())
    assert result.reconciled is True
    assert result.status is ExternalOrderStatus.EXECUTED


def test_not_executed_is_terminal():
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-2", observation("ext-2", ExternalOrderStatus.NOT_EXECUTED)
    )
    assert result.reconciled is True


@pytest.mark.parametrize("status", [ExternalOrderStatus.PENDING, ExternalOrderStatus.UNKNOWN])
def test_ambiguous_external_status_does_not_close_reconciliation(status):
    result = ExternalOrderReconciliationBoundary().reconcile("ext-3", observation("ext-3", status))
    assert result.reconciled is False


def test_external_id_mismatch_fails_closed():
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile("ext-4", observation("other"))


def test_missing_identity_metadata_fails_closed():
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile(
            "ext-4", ExternalOrderObservation("ext-4", ExternalOrderStatus.EXECUTED, "filled")
        )


def test_invalid_external_id_fails_closed():
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile(" ", observation("ext"))
