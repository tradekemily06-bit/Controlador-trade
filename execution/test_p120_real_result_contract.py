from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.models import Signal
from core.operational_state import OperationalState
from core.p111_pre_real_audit import PreRealAuditBoundary
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.p117_real_admission import RealAdmissionStatus
from core.real_privilege_issuer import RealPrivilegeIssuer
from core.risk_state_fingerprint import risk_state_identity
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class MissingExternalIdAdapter:
    def __init__(self): self.calls = 0
    def is_available(self): return True
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
    def current_risk_state(self): return self.state


class SafetyProvider:
    def __init__(self, report: RealSafetyReport): self.report = report
    def current_real_safety(self): return self.report


def _registry(adapter=None):
    registry = BrokerRegistry()
    registry.register("fake", adapter or MissingExternalIdAdapter(), adapter_id="fake-adapter")
    return registry


def _release_audit():
    p111 = PreRealAuditBoundary().audit(
        audit_id="a111", p110_decision="VALIDATED", safety_verified=True,
        risk_verified=True, gateway_present=True, broker_boundary_present=True,
    )
    shadow = ShadowValidationBoundary().validate(
        validation_id="shadow", adapter_available=True, real_safety_ready=True,
        duplicate_blocked=True, kill_switch_blocked=True, real_mode_rejected_by_shadow=True,
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    return RealReleaseAuditBoundary().audit(
        audit_id="a116", pre_real_verified=p111.verified,
        shadow_passed=shadow.passed, safety_ready=safety.ready,
        broker_boundary_ready=True, explicit_real_contract=True,
    )


def _request(request_id="req-1", symbol="TEST", risk_fingerprint=None):
    return ExecutionRequest(
        symbol, Signal.COMPRA, 10.0, 60, ExecutionMode.REAL,
        request_id=request_id, risk_state_fingerprint=risk_fingerprint,
    )


def _snapshot(provider: RiskProvider, symbol="TEST"):
    state = provider.state
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None, operational_state_available=True,
        trades_today=state.trades_today, consecutive_losses=state.consecutive_losses,
        symbol=symbol, timeframe="5m", risk_state_identity=risk_state_identity(state),
        created_at=datetime.now(timezone.utc),
    )


def _authorized_context(request_id="req-1", symbol="TEST", adapter=None):
    registry = _registry(adapter)
    request = _request(request_id, symbol)
    provider = RiskProvider()
    authorization = RealPrivilegeIssuer(BrokerAdapterGateway(registry)).issue_authorization(
        authorization_id="auth", release_audit=_release_audit(), broker="fake",
        request=request, explicit_real_enablement=True,
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    admission = RealPrivilegeIssuer(BrokerAdapterGateway(registry)).issue_admission(
        admission_id="adm", authorization=authorization, release_audit=_release_audit(),
        safety=safety, broker_available=True,
    )
    return registry, provider, authorization, admission, safety


def _gateway(registry, ledger, provider, safety):
    return RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger, provider, SafetyProvider(safety),
    )


def test_accepted_without_external_id_is_unknown_and_persisted(tmp_path: Path):
    registry, provider, authorization, admission, safety = _authorized_context()
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = _gateway(registry, ledger, provider, safety)
    request = _request(risk_fingerprint=risk_state_identity(provider.state))
    result = gateway.execute(
        broker="fake", request_id="req-1", request=request,
        authorization=authorization, admission=admission, safety=safety,
        snapshot=_snapshot(provider),
    )
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("req-1") is ExecutionLedgerStatus.UNKNOWN


def test_invalid_real_snapshot_fails_closed_without_dispatch(tmp_path: Path):
    class MustNotExecuteAdapter:
        def is_available(self): return True
        def execute(self, request): raise AssertionError("REAL executor must not be reached")

    registry, provider, authorization, admission, safety = _authorized_context(adapter=MustNotExecuteAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    result = _gateway(registry, ledger, provider, safety).execute(
        broker="fake", request_id="missing-snapshot", request=_request("missing-snapshot", risk_fingerprint=risk_state_identity(provider.state)),
        authorization=authorization, admission=admission, safety=safety, snapshot=None,
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert ledger.status("missing-snapshot") is None


def test_forged_real_context_is_blocked_before_dispatch(tmp_path: Path):
    registry, provider, authorization, admission, safety = _authorized_context()
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    result = _gateway(registry, ledger, provider, safety).execute(
        broker="fake", request_id="forged-context", request=_request("forged-context", risk_fingerprint=risk_state_identity(provider.state)),
        authorization=type("ForgedAuthorization", (), {"active": True, "broker_id": "fake"})(),
        admission=type("ForgedAdmission", (), {"admitted": True})(),
        safety=type("ForgedSafety", (), {"ready": True})(), snapshot=_snapshot(provider),
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert ledger.status("forged-context") is None


def test_admission_broker_mismatch_is_blocked_before_dispatch(tmp_path: Path):
    registry, provider, authorization, admission, safety = _authorized_context()
    mismatched = replace(admission, broker_id="other", adapter_id="other-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    result = _gateway(registry, ledger, provider, safety).execute(
        broker="fake", request_id="admission-broker-mismatch", request=_request("admission-broker-mismatch", risk_fingerprint=risk_state_identity(provider.state)),
        authorization=authorization, admission=mismatched, safety=safety, snapshot=_snapshot(provider),
    )
    assert result.status == RealGatewayStatus.BLOCKED


def test_admission_audit_mismatch_is_blocked_before_dispatch(tmp_path: Path):
    registry, provider, authorization, admission, safety = _authorized_context()
    mismatched = replace(admission, audit_id="different-audit")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    result = _gateway(registry, ledger, provider, safety).execute(
        broker="fake", request_id="admission-audit-mismatch", request=_request("admission-audit-mismatch", risk_fingerprint=risk_state_identity(provider.state)),
        authorization=authorization, admission=mismatched, safety=safety, snapshot=_snapshot(provider),
    )
    assert result.status == RealGatewayStatus.BLOCKED


def test_real_authorization_symbol_mismatch_is_blocked(tmp_path: Path):
    registry, provider, authorization, admission, safety = _authorized_context()
    mismatched = replace(authorization, symbol="EURUSD")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    result = _gateway(registry, ledger, provider, safety).execute(
        broker="fake", request_id="symbol-mismatch", request=_request("symbol-mismatch", symbol="XAUUSD", risk_fingerprint=risk_state_identity(provider.state)),
        authorization=mismatched, admission=admission, safety=safety, snapshot=_snapshot(provider, "XAUUSD"),
    )
    assert result.status == RealGatewayStatus.BLOCKED


def test_real_adapter_identity_mismatch_is_blocked(tmp_path: Path):
    registry, provider, authorization, admission, safety = _authorized_context()
    mismatched = replace(authorization, adapter_id="authorized-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    result = _gateway(registry, ledger, provider, safety).execute(
        broker="fake", request_id="adapter-mismatch", request=_request("adapter-mismatch", risk_fingerprint=risk_state_identity(provider.state)),
        authorization=mismatched, admission=admission, safety=safety, snapshot=_snapshot(provider),
    )
    assert result.status == RealGatewayStatus.BLOCKED


def test_real_snapshot_symbol_mismatch_is_blocked_before_dispatch(tmp_path: Path):
    adapter = MissingExternalIdAdapter()
    registry, provider, authorization, admission, safety = _authorized_context(adapter=adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    result = _gateway(registry, ledger, provider, safety).execute(
        broker="fake", request_id="snapshot-symbol", request=_request("snapshot-symbol", symbol="TEST", risk_fingerprint=risk_state_identity(provider.state)),
        authorization=authorization, admission=admission, safety=safety, snapshot=_snapshot(provider, "EURUSD"),
    )
    assert result.status == RealGatewayStatus.BLOCKED and adapter.calls == 0


def test_stale_real_safety_is_blocked_before_broker_dispatch(tmp_path: Path):
    registry, provider, authorization, admission, safety = _authorized_context()
    safety_provider = SafetyProvider(safety)
    safety_provider.report = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=False, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    result = _gateway(registry, ExecutionLedger(tmp_path / "ledger.json"), provider, safety).execute(
        broker="fake", request_id="safety-changed", request=_request("safety-changed", risk_fingerprint=risk_state_identity(provider.state)),
        authorization=authorization, admission=admission, safety=safety, snapshot=_snapshot(provider),
    )
    assert result.status == RealGatewayStatus.BLOCKED


def test_active_authorization_cannot_be_constructed_directly():
    with pytest.raises(PermissionError):
        RealExecutionAuthorization("auth", "audit", "fake", "fake-adapter", "req", "TEST", True, True)


def test_legacy_boundary_cannot_issue_active_admission():
    from core.p117_real_admission import RealAdmissionBoundary
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="fake-adapter", request_id="req", symbol="TEST",
    )
    assert admission.status is RealAdmissionStatus.BLOCKED
    assert not admission.admitted
