from pathlib import Path

import pytest

from core.operational_state import OperationalState
from core.p114_real_safety_gate import RealSafetyReport, RealSafetyState
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.real_reconciliation_authority import BrokerReconciliationEvidenceAuthority
from core.risk_state_provider import RiskStateProvider
from core.real_safety_provider import RealSafetyProvider
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.real_gateway import RealExecutionGateway


class QueryPort:
    def __init__(self, status: ExternalOrderStatus, *, request_id: str = "req-1", source: str = "broker", external_id: str = "ext-1", broker: str = "broker", symbol: str = "EURUSD"):
        self.status = status
        self.request_id = request_id
        self.source = source
        self.external_id = external_id
        self.broker = broker
        self.symbol = symbol
        self.calls = 0

    def query_order(self, external_id: str) -> ExternalOrderObservation:
        self.calls += 1
        return ExternalOrderObservation(
            self.external_id, self.status, "authoritative broker observation",
            request_id=self.request_id, evidence_source=self.source,
            broker_id=self.broker, symbol=self.symbol,
        )


class StaticRiskProvider(RiskStateProvider):
    def current_risk_state(self) -> OperationalState:
        return OperationalState(realized_pnl=0.0, trades_today=0, consecutive_losses=0)


class StaticSafetyProvider(RealSafetyProvider):
    def current_real_safety(self) -> RealSafetyReport:
        return RealSafetyReport(RealSafetyState.READY, ())


def gateway(path: Path, authority=None):
    return RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()), ExecutionLedger(path),
        StaticRiskProvider(), StaticSafetyProvider(), reconciliation_evidence_verifier=authority,
    )


def test_broker_evidence_authority_queries_read_only_external_state():
    query = QueryPort(ExternalOrderStatus.EXECUTED)
    authority = BrokerReconciliationEvidenceAuthority(query, evidence_source="broker")
    assert authority.verify(request_id="req-1", evidence_id="ext-1", evidence_source="broker", broker_id="broker", symbol="EURUSD", executed=True)
    assert query.calls == 1


def test_broker_evidence_authority_rejects_mismatched_external_outcome():
    authority = BrokerReconciliationEvidenceAuthority(QueryPort(ExternalOrderStatus.NOT_EXECUTED), evidence_source="broker")
    assert not authority.verify(request_id="req-1", evidence_id="ext-1", evidence_source="broker", broker_id="broker", symbol="EURUSD", executed=True)


def test_broker_evidence_authority_rejects_mismatched_request_identity():
    authority = BrokerReconciliationEvidenceAuthority(QueryPort(ExternalOrderStatus.EXECUTED, request_id="different-request"), evidence_source="broker")
    assert not authority.verify(request_id="req-1", evidence_id="ext-1", evidence_source="broker", broker_id="broker", symbol="EURUSD", executed=True)


def test_broker_evidence_authority_rejects_mismatched_source():
    authority = BrokerReconciliationEvidenceAuthority(QueryPort(ExternalOrderStatus.EXECUTED, source="other-broker"), evidence_source="broker")
    assert not authority.verify(request_id="req-1", evidence_id="ext-1", evidence_source="broker", broker_id="broker", symbol="EURUSD", executed=True)


@pytest.mark.parametrize("field,value", [("broker", "other-broker"), ("symbol", "GBPUSD")])
def test_broker_evidence_authority_rejects_mismatched_operation_identity(field, value):
    kwargs = {field: value}
    authority = BrokerReconciliationEvidenceAuthority(QueryPort(ExternalOrderStatus.EXECUTED, **kwargs), evidence_source="broker")
    assert not authority.verify(request_id="req-1", evidence_id="ext-1", evidence_source="broker", broker_id="broker", symbol="EURUSD", executed=True)


def test_broker_evidence_authority_rejects_missing_binding_metadata():
    class LegacyQuery:
        def query_order(self, external_id: str):
            return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, "legacy")
    authority = BrokerReconciliationEvidenceAuthority(LegacyQuery(), evidence_source="broker")
    assert not authority.verify(request_id="req-1", evidence_id="ext-1", evidence_source="broker", broker_id="broker", symbol="EURUSD", executed=True)


def test_gateway_rejects_untrusted_callable_verifier(tmp_path: Path):
    with pytest.raises(ValueError, match="autoridade de evidência REAL autorizada"):
        gateway(tmp_path / "ledger.json", lambda **kwargs: True)


def test_gateway_refuses_unverified_evidence_and_preserves_unknown(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("req-unknown", broker_id="broker", symbol="EURUSD")
    ledger.mark_unknown("req-unknown")
    authority = BrokerReconciliationEvidenceAuthority(QueryPort(ExternalOrderStatus.NOT_EXECUTED, request_id="req-unknown", external_id="ext-1"), evidence_source="broker")
    with pytest.raises(ValueError, match="não foi confirmada"):
        gateway(path, authority).reconcile_unknown_with_evidence("req-unknown", executed=True, evidence_id="ext-1", evidence_source="broker")
    assert ExecutionLedger(path).status("req-unknown") is ExecutionLedgerStatus.UNKNOWN
    assert ExecutionLedger(path).reconciliation_evidence("req-unknown") is None


def test_gateway_verified_evidence_survives_restart_and_replay_remains_blocked(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("req-verified", broker_id="broker", symbol="EURUSD")
    ledger.mark_unknown("req-verified")
    authority = BrokerReconciliationEvidenceAuthority(QueryPort(ExternalOrderStatus.EXECUTED, request_id="req-verified", external_id="ext-verified"), evidence_source="broker")
    gateway(path, authority).reconcile_unknown_with_evidence("req-verified", executed=True, evidence_id="ext-verified", evidence_source="broker")
    restored = ExecutionLedger(path)
    assert restored.status("req-verified") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert restored.execution_context("req-verified") == {"broker_id": "broker", "symbol": "EURUSD", "external_id": None}
    with pytest.raises(ValueError):
        gateway(path, authority).reconcile_unknown_with_evidence("req-verified", executed=True, evidence_id="ext-verified", evidence_source="broker")


def test_gateway_rejects_external_id_different_from_persisted_broker_id(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve_real("req-id", broker_id="broker", symbol="EURUSD")
    ledger.mark_accepted_real("req-id", external_id="ext-original")
    ledger.mark_unknown("req-id")
    authority = BrokerReconciliationEvidenceAuthority(QueryPort(ExternalOrderStatus.EXECUTED, request_id="req-id", external_id="ext-other"), evidence_source="broker")
    with pytest.raises(ValueError, match="external_id difere"):
        gateway(path, authority).reconcile_unknown_with_evidence("req-id", executed=True, evidence_id="ext-other", evidence_source="broker")


def test_gateway_rejects_unverified_legacy_reconciliation(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-legacy")
    ledger.mark_unknown("req-legacy")
    with pytest.raises(RuntimeError, match="evidência externa autoritativa"):
        gateway(path).reconcile_unknown("req-legacy", executed=True)
    assert ExecutionLedger(path).status("req-legacy") is ExecutionLedgerStatus.UNKNOWN
