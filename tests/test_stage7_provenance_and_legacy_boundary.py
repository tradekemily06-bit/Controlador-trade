from pathlib import Path

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.models import Signal
from core.operational_state import OperationalState
from core.p116_real_release_audit import RealReleaseAudit, RealReleaseAuditBoundary, ReleaseAuditStatus
from core.p117_real_admission import RealAdmission, RealAdmissionBoundary, RealAdmissionStatus
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.risk_state_fingerprint import risk_state_identity
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus
from core.p114_real_safety_gate import RealSafetyGate
from core.global_operational_barrier import GlobalOperationalBarrier
from core.risk_state_provider import RiskStateProvider
from core.real_safety_provider import RealSafetyProvider


class _Adapter:
    adapter_id = "adapter"

    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "accepted", "ext-1")


class _Risk(RiskStateProvider):
    def current_risk_state(self):
        return OperationalState(
            balance=1000.0, equity=1000.0, realized_pnl=0.0,
            unrealized_pnl=0.0, trades_today=0, consecutive_losses=0,
            open_positions=0, net_position=0.0, exposure=0.0,
            market_open=True,
        )


class _Safety(RealSafetyProvider):
    def current_real_safety(self):
        return RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True,
            market_healthy=True, recovery_safe=True,
            risk_approved=True, broker_available=True,
        )


def _verified_audit():
    return RealReleaseAuditBoundary().audit(
        audit_id="audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True,
        explicit_real_contract=True,
    )


def _active_authorization():
    return RealAuthorizationIssuer().issue(
        audit=_verified_audit(), authorization_id="auth", audit_id="audit",
        broker_id="broker", adapter_id="adapter", request_id="req",
        symbol="TEST", explicit_approval=True,
    )


def _admitted():
    auth = _active_authorization()
    audit = _verified_audit()
    return RealAdmissionBoundary().admit(
        admission_id="admission", audit_id="audit", audit_verified=audit,
        authorization_active=auth, safety_ready=True,
        broker_available=True, broker_id="broker", adapter_id="adapter",
        request_id="req", symbol="TEST",
    )

def _state():
    return OperationalState(
        balance=1000.0, equity=1000.0, realized_pnl=0.0,
        unrealized_pnl=0.0, trades_today=0, consecutive_losses=0,
        open_positions=0, net_position=0.0, exposure=0.0,
        market_open=True,
    )


def _snapshot():
    state = _state()
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None,
        operational_state_available=True, trades_today=0,
        consecutive_losses=0, symbol="TEST", timeframe="5m",
        risk_state_identity=risk_state_identity(state),
    )


def test_field_identical_real_authorization_is_not_active():
    fabricated = RealExecutionAuthorization(
        "auth", "audit", "broker", "adapter", "req", "TEST", True, True,
    )
    assert fabricated.active is False


def test_fabricated_verified_audit_cannot_issue_real_authorization():
    fabricated = RealReleaseAudit(
        "audit", ReleaseAuditStatus.VERIFIED,
        ("P111", "P112", "P113", "P114", "P115"), (),
    )
    with pytest.raises(ValueError, match="fronteira"):
        RealAuthorizationIssuer().issue(
            audit=fabricated, authorization_id="auth", audit_id="audit",
            broker_id="broker", adapter_id="adapter", request_id="req",
            symbol="TEST", explicit_approval=True,
        )


def test_field_identical_admitted_object_is_not_admitted():
    fabricated = RealAdmission(
        "admission", "audit", RealAdmissionStatus.ADMITTED,
        "broker", "adapter", "req", "TEST", (),
    )
    assert fabricated.admitted is False


def test_legacy_analysis_snapshot_cannot_cross_real_gateway_boundary(tmp_path: Path):
    from analysis.decision_snapshot import DecisionSnapshotBuilder
    from core.models import AnalysisResult

    legacy = DecisionSnapshotBuilder().build(
        AnalysisResult(Signal.COMPRA, 90.0, "confirmed", True, "TEST", "5m")
    )
    assert not isinstance(legacy, DecisionSnapshot)

    registry = BrokerRegistry()
    adapter = _Adapter()
    registry.register("broker", adapter, adapter_id="adapter")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"),
        _Risk(), _Safety(), operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )
    auth = _active_authorization()
    admission = _admitted()
    safety = _Safety().current_real_safety()
    state = _state()
    request = ExecutionRequest(
        "TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL,
        request_id="req", risk_state_fingerprint=risk_state_identity(state),
    )
    result = gateway.execute(
        broker="broker", request_id="req", request=request,
        authorization=auth, admission=admission, safety=safety,
        snapshot=legacy,
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
