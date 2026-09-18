from __future__ import annotations

from pathlib import Path

from core.decision_snapshot import DecisionSnapshot
from core.models import Signal
from core.operational_state import OperationalState
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.p117_real_admission import RealAdmissionBoundary
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.risk_state_fingerprint import risk_state_identity
from core.risk_state_provider import RiskStateProvider
from core.real_safety_provider import RealSafetyProvider
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class CountingAdapter:
    adapter_id = "stage7-fake-adapter"

    def __init__(self) -> None:
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls += 1
        return ExecutionResult(True, "must not dispatch", "should-not-exist")


class Risk(RiskStateProvider):
    def current_risk_state(self) -> OperationalState:
        return OperationalState(
            realized_pnl=0.0,
            trades_today=0,
            consecutive_losses=0,
        )


class Safety(RealSafetyProvider):
    def current_real_safety(self) -> RealSafetyReport:
        return RealSafetyGate().evaluate(
            authorization_active=True,
            kill_switch_clear=True,
            market_healthy=True,
            recovery_safe=True,
            risk_approved=True,
            broker_available=True,
        )


def _snapshot(state: OperationalState) -> DecisionSnapshot:
    identity = risk_state_identity(state)
    return DecisionSnapshot(
        signal="COMPRA",
        analysis_score=90.0,
        confirmed=True,
        quality_score=90.0,
        quality_level="FORTE",
        actionable=True,
        decision="EXECUTAR",
        decision_reason="stage7 test",
        market_context="NEUTRO",
        market_direction="ALTA",
        market_score=80.0,
        operational_state_available=True,
        trades_today=0,
        consecutive_losses=0,
        symbol="TEST",
        timeframe="5m",
        risk_state_identity=identity,
    )


def _authorization(request_id: str):
    audit = RealReleaseAuditBoundary().audit(
        audit_id="stage7-audit",
        pre_real_verified=True,
        shadow_passed=True,
        safety_ready=True,
        broker_boundary_ready=True,
        explicit_real_contract=True,
    )
    return RealAuthorizationIssuer().issue(
        audit=audit,
        authorization_id="stage7-auth",
        audit_id="stage7-audit",
        broker_id="stage7-broker",
        adapter_id="stage7-fake-adapter",
        request_id=request_id,
        symbol="TEST",
        explicit_approval=True,
    )


def _admission(request_id: str):
    auth = _authorization(request_id)
    audit = RealReleaseAuditBoundary().audit(
        audit_id="stage7-audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    return RealAdmissionBoundary().admit(
        admission_id="stage7-admission",
        audit_id="stage7-audit",
        audit_verified=audit,
        authorization_active=auth,
        safety_ready=True,
        broker_available=True,
        broker_id="stage7-broker",
        adapter_id="stage7-fake-adapter",
        request_id=request_id,
        symbol="TEST",
    )

def test_real_dispatch_fails_closed_when_global_barrier_is_missing(tmp_path: Path):
    request_id = "stage7-no-global-barrier"
    state = Risk().current_risk_state()
    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("stage7-broker", adapter, adapter_id=adapter.adapter_id)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
        Risk(),
        Safety(),
    )

    request = ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=1.0,
        duration_seconds=60,
        mode=ExecutionMode.REAL,
        request_id=request_id,
        risk_state_fingerprint=risk_state_identity(state),
    )
    result = gateway.execute(
        broker="stage7-broker",
        request_id=request_id,
        request=request,
        authorization=_authorization(request_id),
        admission=_admission(request_id),
        safety=Safety().current_real_safety(),
        snapshot=_snapshot(state),
    )

    assert result.status == RealGatewayStatus.BLOCKED
    assert "barreira operacional global" in result.message.lower()
    assert adapter.calls == 0
    assert ExecutionLedger(tmp_path / "ledger.json").status(request_id) is None
