from pathlib import Path

import pytest

from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.operational_state import OperationalState
from core.p114_real_safety_gate import RealSafetyReport, RealSafetyState
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.real_reconciliation_authority import BrokerReconciliationEvidenceAuthority
from core.risk_state_provider import RiskStateProvider
from core.real_safety_provider import RealSafetyProvider
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.real_gateway import RealExecutionGateway


class Risk(RiskStateProvider):
    def current_risk_state(self):
        return OperationalState(realized_pnl=0.0, trades_today=0, consecutive_losses=0)


class Safety(RealSafetyProvider):
    def current_real_safety(self):
        return RealSafetyReport(RealSafetyState.READY, ())


class Query:
    def query_order(self, external_id: str):
        return ExternalOrderObservation(
            external_id,
            ExternalOrderStatus.EXECUTED,
            "ok",
            request_id="req",
            evidence_source="broker",
        )


def barrier():
    return GlobalOperationalBarrier((SafetyComponent("test", True, "ok"),))


def make_gateway(tmp_path: Path):
    return RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ExecutionLedger(tmp_path / "ledger.json"),
        Risk(),
        Safety(),
    )


def test_barrier_provider_cannot_be_replaced_after_binding(tmp_path: Path):
    gateway = make_gateway(tmp_path)
    gateway.set_operational_barrier_provider(barrier)
    with pytest.raises(RuntimeError, match="substituição não permitida"):
        gateway.set_operational_barrier_provider(lambda: barrier())


def test_barrier_provider_cannot_be_removed_after_binding(tmp_path: Path):
    gateway = make_gateway(tmp_path)
    gateway.set_operational_barrier_provider(barrier)
    with pytest.raises(RuntimeError, match="substituição não permitida"):
        gateway.set_operational_barrier_provider(None)


def test_evidence_authority_cannot_be_replaced_after_binding(tmp_path: Path):
    gateway = make_gateway(tmp_path)
    authority = BrokerReconciliationEvidenceAuthority(Query(), evidence_source="broker")
    gateway.set_reconciliation_evidence_verifier(authority)
    with pytest.raises(RuntimeError, match="substituição não permitida"):
        gateway.set_reconciliation_evidence_verifier(
            BrokerReconciliationEvidenceAuthority(Query(), evidence_source="broker")
        )


def test_configuration_freezes_after_dispatch_attempt(tmp_path: Path):
    gateway = make_gateway(tmp_path)
    # Any REAL dispatch attempt freezes mutable configuration before returning,
    # including a fail-closed validation result.
    from execution.ports import ExecutionMode, ExecutionRequest
    from core.models import Signal
    from core.decision_snapshot import DecisionSnapshot
    from core.risk_state_fingerprint import risk_state_identity
    state = Risk().current_risk_state()
    snapshot = DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="FORTE", actionable=True,
        decision="EXECUTAR", decision_reason="teste", market_context="NEUTRO",
        market_direction="ALTA", market_score=80.0, operational_state_available=True,
        trades_today=0, consecutive_losses=0, symbol="TEST", timeframe="5m",
        risk_state_identity=risk_state_identity(state),
    )
    request = ExecutionRequest(
        symbol="TEST", signal=Signal.COMPRA, amount=1.0, duration_seconds=60,
        mode=ExecutionMode.REAL, request_id="req", risk_state_fingerprint=risk_state_identity(state),
    )
    # Missing authorization/admission is intentionally enough to exercise the
    # configuration-freeze boundary without ever reaching a broker adapter.
    result = gateway.execute(
        broker="broker", request_id="req", request=request,
        authorization=object(), admission=object(), safety=object(), snapshot=snapshot,
    )
    assert result.status == "BLOCKED"
    with pytest.raises(RuntimeError, match="não pode ser substituída"):
        gateway.set_operational_barrier_provider(barrier)
