import pytest

from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)


def test_terminal_external_status_reconciles():
    boundary = ExternalOrderReconciliationBoundary()
    result = boundary.reconcile(
        "ext-1",
        ExternalOrderObservation("ext-1", ExternalOrderStatus.EXECUTED, "filled"),
    )
    assert result.reconciled is True
    assert result.status is ExternalOrderStatus.EXECUTED


def test_not_executed_is_terminal():
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-2",
        ExternalOrderObservation("ext-2", ExternalOrderStatus.NOT_EXECUTED, "cancelled"),
    )
    assert result.reconciled is True


@pytest.mark.parametrize("status", [ExternalOrderStatus.PENDING, ExternalOrderStatus.UNKNOWN])
def test_ambiguous_external_status_does_not_close_reconciliation(status):
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-3", ExternalOrderObservation("ext-3", status, "not final"),
    )
    assert result.reconciled is False


def test_external_id_mismatch_fails_closed():
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile(
            "ext-4",
            ExternalOrderObservation("other", ExternalOrderStatus.EXECUTED, "filled"),
        )


def test_invalid_external_id_fails_closed():
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile(
            " ",
            ExternalOrderObservation("ext", ExternalOrderStatus.UNKNOWN, "unknown"),
        )

def test_request_bound_reconciliation_requires_matching_request_id():
    observation = ExternalOrderObservation("ext-5", ExternalOrderStatus.EXECUTED, "filled", request_id="req-5")
    result = ExternalOrderReconciliationBoundary().reconcile_for_request("req-5", observation)
    assert result.reconciled is True
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile_for_request("other", observation)


def test_request_bound_reconciliation_can_confirm_not_executed_without_external_id():
    observation = ExternalOrderObservation(None, ExternalOrderStatus.NOT_EXECUTED, "no order found", request_id="req-6")
    result = ExternalOrderReconciliationBoundary().reconcile_for_request("req-6", observation)
    assert result.reconciled is True
    assert result.external_id is None


def test_request_bound_reconciliation_keeps_ambiguous_status_nonterminal():
    observation = ExternalOrderObservation(None, ExternalOrderStatus.PENDING, "still pending", request_id="req-7")
    result = ExternalOrderReconciliationBoundary().reconcile_for_request("req-7", observation)
    assert result.reconciled is False
