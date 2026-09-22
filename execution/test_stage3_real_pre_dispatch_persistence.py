from __future__ import annotations

from core.decision_snapshot import DecisionSnapshot
from core.global_operational_barrier import GlobalOperationalBarrier
from core.models import Signal
from core.operational_state import OperationalState
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.risk_state_fingerprint import risk_state_identity
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class SequencedRiskProvider:
    def __init__(self, first, second):
        self.states = [first, second]

    def current_risk_state(self):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


class SafetyProvider:
    def current_real_safety(self):
        return RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True, market_healthy=True,
            recovery_safe=True, risk_approved=True, broker_available=True,
        )


class Adapter:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "accepted", "must-not-run")


def state(balance):
    return OperationalState(
        balance=balance, equity=1000.0, realized_pnl=0.0, unrealized_pnl=0.0,
        trades_today=0, consecutive_losses=0, open_positions=0, net_position=0.0,
        exposure=0.0, market_open=True,
    )


def authorization(request_id):
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    return RealAuthorizationIssuer().issue(
        audit=audit, authorization_id="auth", audit_id="audit",
        broker_id="fake", adapter_id="fake-adapter", request_id=request_id,
        symbol="TEST", explicit_approval=True,
    )


def test_post_reservation_pre_dispatch_risk_change_is_rejected_not_unknown(tmp_path):
    first, changed = state(1000.0), state(999.0)
    provider = SequencedRiskProvider(first, changed)
    adapter = Adapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter, adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger, provider, SafetyProvider(),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )
    rid = "post-reservation-risk-change"
    auth = authorization(rid)
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=audit,
        authorization_active=auth, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="fake-adapter", request_id=rid, symbol="TEST",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=auth.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest(
        "TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, rid,
        risk_state_fingerprint=risk_state_identity(first),
    )
    snapshot = DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True, quality_score=90.0,
        quality_level="HIGH", actionable=True, decision="COMPRA", decision_reason="test",
        market_context=None, market_direction=None, market_score=None,
        operational_state_available=True, trades_today=0, consecutive_losses=0,
        symbol="TEST", timeframe="5m", risk_state_identity=risk_state_identity(first),
    )
    result = gateway.execute(
        broker="fake", request_id=rid, request=request, authorization=auth,
        admission=admission, safety=safety, snapshot=snapshot,
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert ledger.status(rid) is ExecutionLedgerStatus.REJECTED
