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


def test_reconciliation_binds_observation_to_expected_execution_identity():
    boundary = ExternalOrderReconciliationBoundary()
    with pytest.raises(ValueError):
        boundary.reconcile("ext-1", observation(), expected_request_id="other-request")
    with pytest.raises(ValueError):
        boundary.reconcile("ext-1", observation(), expected_broker_id="other-broker")
    with pytest.raises(ValueError):
        boundary.reconcile("ext-1", observation(), expected_symbol="GBPUSD")


def test_reconciliation_rejects_blank_message():
    with pytest.raises(ValueError):
        boundary = ExternalOrderReconciliationBoundary()
        boundary.reconcile(
            "ext-1",
            ExternalOrderObservation(
                "ext-1", ExternalOrderStatus.EXECUTED, " ",
                request_id="req-1", evidence_source="broker", broker_id="broker", symbol="EURUSD"
            ),
        )


from core.real_reconciliation_authority import BrokerReconciliationEvidenceAuthority


class _QueryPort:
    def query_order(self, external_id: str) -> ExternalOrderObservation:
        return observation(external_id)


def test_evidence_authority_rejects_non_boolean_executed_flag():
    authority = BrokerReconciliationEvidenceAuthority(_QueryPort(), evidence_source="broker")
    assert authority.verify(
        request_id="req-1",
        evidence_id="ext-1",
        evidence_source="broker",
        broker_id="broker",
        symbol="EURUSD",
        executed="false",  # type: ignore[arg-type]
    ) is False


def test_evidence_authority_accepts_strict_boolean_outcome():
    authority = BrokerReconciliationEvidenceAuthority(_QueryPort(), evidence_source="broker")
    assert authority.verify(
        request_id="req-1",
        evidence_id="ext-1",
        evidence_source="broker",
        broker_id="broker",
        symbol="EURUSD",
        executed=True,
    ) is True
