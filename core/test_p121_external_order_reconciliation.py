import pytest

from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)


class FakeQueryPort:
    def __init__(self, observation):
        self.observation = observation
        self.calls = 0

    def query_order(self, external_id):
        self.calls += 1
        assert external_id == self.observation.external_id
        return self.observation


def test_terminal_external_status_reconciles():
    port = FakeQueryPort(
        ExternalOrderObservation("ext-1", ExternalOrderStatus.EXECUTED, "filled")
    )
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-1",
        query_port=port,
    )
    assert result.reconciled is True
    assert result.status is ExternalOrderStatus.EXECUTED
    assert port.calls == 1


def test_not_executed_is_terminal():
    port = FakeQueryPort(
        ExternalOrderObservation("ext-2", ExternalOrderStatus.NOT_EXECUTED, "cancelled")
    )
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-2",
        query_port=port,
    )
    assert result.reconciled is True


@pytest.mark.parametrize("status", [ExternalOrderStatus.PENDING, ExternalOrderStatus.UNKNOWN])
def test_ambiguous_external_status_does_not_close_reconciliation(status):
    port = FakeQueryPort(ExternalOrderObservation("ext-3", status, "not final"))
    result = ExternalOrderReconciliationBoundary().reconcile(
        "ext-3",
        query_port=port,
    )
    assert result.reconciled is False


def test_external_id_mismatch_from_broker_fails_closed():
    port = FakeQueryPort(
        ExternalOrderObservation("other", ExternalOrderStatus.EXECUTED, "filled")
    )
    with pytest.raises(AssertionError):
        ExternalOrderReconciliationBoundary().reconcile(
            "ext-4",
            query_port=port,
        )


def test_invalid_external_id_fails_closed():
    with pytest.raises(ValueError):
        ExternalOrderReconciliationBoundary().reconcile(
            " ",
            query_port=FakeQueryPort(
                ExternalOrderObservation("ext", ExternalOrderStatus.UNKNOWN, "unknown")
            ),
        )


def test_local_observation_cannot_be_supplied_as_reconciliation_evidence():
    with pytest.raises(TypeError):
        ExternalOrderReconciliationBoundary().reconcile(
            "ext-5",
            ExternalOrderObservation("ext-5", ExternalOrderStatus.EXECUTED, "forged"),
        )
