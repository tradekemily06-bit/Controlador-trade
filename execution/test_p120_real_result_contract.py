from pathlib import Path

from core.decision_snapshot import DecisionSnapshot
from core.models import Signal
from core.operational_state import OperationalState
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.p117_real_admission import RealAdmissionBoundary
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.global_operational_barrier import GlobalOperationalBarrier
from core.risk_state_fingerprint import risk_state_identity
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class MissingExternalIdAdapter:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "accepted but no durable reference", None)


class RiskProvider:
    def __init__(self):
        self.state = OperationalState(
            balance=1000.0, equity=1000.0, realized_pnl=0.0,
            unrealized_pnl=0.0, trades_today=0, consecutive_losses=0,
            open_positions=0, net_position=0.0, exposure=0.0, market_open=True,
        )

    def current_risk_state(self):
        return self.state


class SafetyProvider:
    def __init__(self, report: RealSafetyReport):
        self.report = report

    def current_real_safety(self):
        return self.report


def _snapshot(provider: RiskProvider) -> DecisionSnapshot:
    state = provider.state
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None, operational_state_available=True,
        trades_today=state.trades_today, consecutive_losses=state.consecutive_losses,
        symbol="TEST", timeframe="5m", risk_state_identity=risk_state_identity(state),
    )


def _authorized_context(request_id="req-1", symbol="TEST", broker_id="fake", adapter_id="fake-adapter"):
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    authorization = RealAuthorizationIssuer().issue(
        audit=audit, authorization_id="auth", audit_id="audit", broker_id=broker_id,
        adapter_id=adapter_id, request_id=request_id, symbol=symbol, explicit_approval=True,
    )
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=audit,
        authorization_active=authorization, safety_ready=True,
        broker_available=True, broker_id=broker_id, adapter_id=adapter_id,
        request_id=request_id, symbol=symbol,
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=authorization.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    return authorization, admission, safety


def _gateway(registry, ledger, provider, safety):
    return RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger, provider, SafetyProvider(safety),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )


def _request(request_id="req-1", symbol="TEST", risk_fingerprint=None):
    return ExecutionRequest(
        symbol, Signal.COMPRA, 10.0, 60, ExecutionMode.REAL,
        request_id=request_id, risk_state_fingerprint=risk_fingerprint,
    )


def test_accepted_without_external_id_is_unknown_and_persisted(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", MissingExternalIdAdapter(), adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    provider = RiskProvider()
    authorization, admission, safety = _authorized_context()
    gateway = _gateway(registry, ledger, provider, safety)
    request = _request(risk_fingerprint=risk_state_identity(provider.state))
    result = gateway.execute(broker="fake", request_id="req-1", request=request,
                             authorization=authorization, admission=admission, safety=safety,
                             snapshot=_snapshot(provider))
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("req-1") is ExecutionLedgerStatus.UNKNOWN


def test_invalid_real_snapshot_fails_closed_without_dispatch(tmp_path: Path):
    class MustNotExecuteAdapter:
        def is_available(self): return True
        def execute(self, request): raise AssertionError("REAL executor must not be reached without a valid decision snapshot")
    registry = BrokerRegistry(); registry.register("fake", MustNotExecuteAdapter(), adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); provider = RiskProvider()
    authorization, admission, safety = _authorized_context(request_id="missing-snapshot")
    gateway = _gateway(registry, ledger, provider, safety)
    request = _request("missing-snapshot", risk_fingerprint=risk_state_identity(provider.state))
    result = gateway.execute(broker="fake", request_id="missing-snapshot", request=request,
                             authorization=authorization, admission=admission, safety=safety, snapshot=None)
    assert result.status == RealGatewayStatus.BLOCKED
    assert "snapshot" in result.message
    assert ledger.status("missing-snapshot") is None


def test_forged_real_context_is_blocked_before_dispatch(tmp_path: Path):
    class MustNotExecuteAdapter:
        def is_available(self): return True
        def execute(self, request): raise AssertionError("forged REAL context must never reach the broker adapter")
    registry = BrokerRegistry(); registry.register("fake", MustNotExecuteAdapter(), adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); provider = RiskProvider()
    authorization, admission, safety = _authorized_context(request_id="forged-context")
    gateway = _gateway(registry, ledger, provider, safety)
    request = _request("forged-context", risk_fingerprint=risk_state_identity(provider.state))
    result = gateway.execute(broker="fake", request_id="forged-context", request=request,
                             authorization=type("ForgedAuthorization", (), {"active": True, "broker_id": "fake"})(),
                             admission=type("ForgedAdmission", (), {"admitted": True})(),
                             safety=type("ForgedSafety", (), {"ready": True})(), snapshot=_snapshot(provider))
    assert result.status == RealGatewayStatus.BLOCKED
    assert "contexto" in result.message
    assert ledger.status("forged-context") is None


def test_stale_real_safety_is_blocked_before_broker_dispatch(tmp_path: Path):
    registry = BrokerRegistry(); adapter = MissingExternalIdAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); provider = RiskProvider()
    authorization, admission, safety = _authorized_context(); safety_provider = SafetyProvider(safety)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, provider, safety_provider)
    safety_provider.report = RealSafetyGate().evaluate(authorization_active=True, kill_switch_clear=False,
        market_healthy=True, recovery_safe=True, risk_approved=True, broker_available=True)
    request = _request(risk_fingerprint=risk_state_identity(provider.state))
    result = gateway.execute(broker="fake", request_id="req-1", request=request,
                             authorization=authorization, admission=admission, safety=safety, snapshot=_snapshot(provider))
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.is_available()


def test_safety_provider_failure_is_unknown_without_leaking_detail(tmp_path: Path):
    class BrokenSafetyProvider:
        def current_real_safety(self): raise RuntimeError("SECRET_SAFETY_PROVIDER_DETAIL")
    registry = BrokerRegistry(); adapter = MissingExternalIdAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); provider = RiskProvider()
    authorization, admission, safety = _authorized_context()
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, provider, BrokenSafetyProvider(), operational_barrier_provider=lambda: GlobalOperationalBarrier())
    request = _request(risk_fingerprint=risk_state_identity(provider.state))
    result = gateway.execute(broker="fake", request_id="req-1", request=request,
                             authorization=authorization, admission=admission, safety=safety, snapshot=_snapshot(provider))
    assert result.status == RealGatewayStatus.UNKNOWN
    assert "SECRET_SAFETY_PROVIDER_DETAIL" not in result.message
    assert "RuntimeError" in result.message


def test_admission_broker_mismatch_is_blocked_before_dispatch(tmp_path: Path):
    class MustNotExecuteAdapter:
        def is_available(self): return True
        def execute(self, request): raise AssertionError("mismatched REAL admission must never reach the broker adapter")
    registry = BrokerRegistry(); registry.register("fake", MustNotExecuteAdapter(), adapter_id="fake-adapter"); registry.register("other", MustNotExecuteAdapter(), adapter_id="other-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); provider = RiskProvider(); authorization, _, safety = _authorized_context()
    other_audit = RealReleaseAuditBoundary().audit(
        audit_id="audit-other", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    other_auth = RealAuthorizationIssuer().issue(
        audit=other_audit, authorization_id="auth-other", audit_id="audit-other",
        broker_id="other", adapter_id="other-adapter", request_id="admission-broker-mismatch",
        symbol="TEST", explicit_approval=True,
    )
    mismatched_admission = RealAdmissionBoundary().admit(
        admission_id="adm-other", audit_id="audit-other", audit_verified=other_audit,
        authorization_active=other_auth, safety_ready=True, broker_available=True,
        broker_id="other", adapter_id="other-adapter",
        request_id="admission-broker-mismatch", symbol="TEST",
    )
    gateway = _gateway(registry, ledger, provider, safety); request = _request("admission-broker-mismatch", risk_fingerprint=risk_state_identity(provider.state))
    result = gateway.execute(broker="fake", request_id="admission-broker-mismatch", request=request,
        authorization=_authorized_context("admission-broker-mismatch")[0], admission=mismatched_admission,
        safety=safety, snapshot=_snapshot(provider))
    assert result.status == RealGatewayStatus.BLOCKED
    assert "admissão REAL" in result.message or "adapter" in result.message
    assert ledger.status("admission-broker-mismatch") is None


def test_admission_audit_mismatch_is_blocked_before_dispatch(tmp_path: Path):
    class MustNotExecuteAdapter:
        def is_available(self): return True
        def execute(self, request): raise AssertionError("mismatched REAL audit context must never reach the broker adapter")
    registry = BrokerRegistry(); registry.register("fake", MustNotExecuteAdapter(), adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); provider = RiskProvider(); authorization, _, safety = _authorized_context()
    other_audit = RealReleaseAuditBoundary().audit(
        audit_id="different-audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    other_auth = RealAuthorizationIssuer().issue(
        audit=other_audit, authorization_id="auth-different", audit_id="different-audit",
        broker_id="fake", adapter_id="fake-adapter", request_id="admission-audit-mismatch",
        symbol="TEST", explicit_approval=True,
    )
    mismatched_admission = RealAdmissionBoundary().admit(
        admission_id="adm-mismatch", audit_id="different-audit", audit_verified=other_audit,
        authorization_active=other_auth, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="fake-adapter",
        request_id="admission-audit-mismatch", symbol="TEST",
    )
    gateway = _gateway(registry, ledger, provider, safety); request = _request("admission-audit-mismatch", risk_fingerprint=risk_state_identity(provider.state))
    result = gateway.execute(broker="fake", request_id="admission-audit-mismatch", request=request,
        authorization=_authorized_context("admission-audit-mismatch")[0], admission=mismatched_admission,
        safety=safety, snapshot=_snapshot(provider))
    assert result.status == RealGatewayStatus.BLOCKED
    assert "auditoria" in result.message
    assert ledger.status("admission-audit-mismatch") is None


def test_real_authorization_symbol_mismatch_is_blocked(tmp_path: Path):
    adapter = MissingExternalIdAdapter(); registry = BrokerRegistry(); registry.register("fake", adapter, adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); provider = RiskProvider(); _, admission, safety = _authorized_context(request_id="symbol-mismatch")
    authorization, _, _ = _authorized_context(request_id="symbol-mismatch", symbol="EURUSD")
    request = _request("symbol-mismatch", symbol="XAUUSD", risk_fingerprint=risk_state_identity(provider.state))
    result = _gateway(registry, ledger, provider, safety).execute(broker="fake", request_id="symbol-mismatch", request=request,
        authorization=authorization, admission=admission, safety=safety, snapshot=_snapshot(provider))
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_adapter_identity_mismatch_is_blocked(tmp_path: Path):
    adapter = MissingExternalIdAdapter(); registry = BrokerRegistry(); registry.register("fake", adapter, adapter_id="resolved-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); provider = RiskProvider()
    authorization, admission, safety = _authorized_context(request_id="adapter-mismatch", adapter_id="authorized-adapter")
    request = _request("adapter-mismatch", risk_fingerprint=risk_state_identity(provider.state))
    result = _gateway(registry, ledger, provider, safety).execute(broker="fake", request_id="adapter-mismatch", request=request,
        authorization=authorization, admission=admission, safety=safety, snapshot=_snapshot(provider))
    assert result.status == RealGatewayStatus.BLOCKED
