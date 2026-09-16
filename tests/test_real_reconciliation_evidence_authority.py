from pathlib import Path

import pytest

from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.real_reconciliation_authority import BrokerReconciliationEvidenceAuthority
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.real_gateway import RealExecutionGateway


class QueryPort:
    def __init__(self, status: ExternalOrderStatus):
        self.status = status
        self.calls = 0

    def query_order(self, external_id: str) -> ExternalOrderObservation:
        self.calls += 1
        return ExternalOrderObservation(external_id, self.status, "authoritative broker observation")


def gateway(path: Path, verifier):
    return RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ExecutionLedger(path),
        reconciliation_evidence_verifier=verifier,
    )


def test_broker_evidence_authority_queries_read_only_external_state():
    query = QueryPort(ExternalOrderStatus.EXECUTED)
    authority = BrokerReconciliationEvidenceAuthority(query)
    assert authority.verify(request_id="req-1", evidence_id="ext-1", evidence_source="broker", executed=True)
    assert query.calls == 1


def test_broker_evidence_authority_rejects_mismatched_external_outcome():
    query = QueryPort(ExternalOrderStatus.NOT_EXECUTED)
    authority = BrokerReconciliationEvidenceAuthority(query)
    assert not authority.verify(request_id="req-1", evidence_id="ext-1", evidence_source="broker", executed=True)


def test_gateway_refuses_unverified_evidence_and_preserves_unknown(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-unknown")
    ledger.mark_unknown("req-unknown")
    verifier = lambda **kwargs: False
    gateway_instance = gateway(path, verifier)

    with pytest.raises(ValueError, match="não foi confirmada"):
        gateway_instance.reconcile_unknown_with_evidence(
            "req-unknown", executed=True, evidence_id="ext-1", evidence_source="broker"
        )

    assert ExecutionLedger(path).status("req-unknown") is ExecutionLedgerStatus.UNKNOWN
    assert ExecutionLedger(path).reconciliation_evidence("req-unknown") is None


def test_gateway_verified_evidence_survives_restart_and_replay_remains_blocked(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-verified")
    ledger.mark_unknown("req-verified")

    verifier = lambda **kwargs: kwargs["evidence_id"] == "ext-verified" and kwargs["executed"] is True
    gateway(path, verifier).reconcile_unknown_with_evidence(
        "req-verified", executed=True, evidence_id="ext-verified", evidence_source="broker"
    )

    restored = ExecutionLedger(path)
    assert restored.status("req-verified") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert restored.reconciliation_evidence("req-verified") == {
        "evidence_id": "ext-verified",
        "evidence_source": "broker",
    }
    with pytest.raises(ValueError):
        gateway(path, verifier).reconcile_unknown_with_evidence(
            "req-verified", executed=True, evidence_id="ext-verified", evidence_source="broker"
        )
