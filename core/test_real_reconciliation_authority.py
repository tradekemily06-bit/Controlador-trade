from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.real_reconciliation_authority import BrokerReconciliationEvidenceAuthority


class Query:
    def __init__(self, status):
        self.status = status

    def query_order(self, external_id):
        return ExternalOrderObservation(external_id, self.status, "broker")


def test_authority_requires_terminal_broker_observation():
    authority = BrokerReconciliationEvidenceAuthority(Query(ExternalOrderStatus.EXECUTED))
    assert authority.verify(request_id="req", evidence_id="ext", evidence_source="broker", executed=True)


def test_authority_rejects_mismatched_broker_observation():
    authority = BrokerReconciliationEvidenceAuthority(Query(ExternalOrderStatus.NOT_EXECUTED))
    assert not authority.verify(request_id="req", evidence_id="ext", evidence_source="broker", executed=True)


def test_authority_rejects_ambiguous_broker_observation():
    authority = BrokerReconciliationEvidenceAuthority(Query(ExternalOrderStatus.UNKNOWN))
    assert not authority.verify(request_id="req", evidence_id="ext", evidence_source="broker", executed=True)
