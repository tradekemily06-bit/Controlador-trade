import pytest

from core.models import Signal
from core.p111_pre_real_audit import PreRealAuditBoundary
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.p117_real_admission import RealAdmissionBoundary
from core.real_privilege_issuer import RealPrivilegeIssuer
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.ports import ExecutionMode, ExecutionRequest


class FakeAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        return None


def _registry():
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter(), adapter_id="fake-adapter")
    return registry


def _issuer():
    return RealPrivilegeIssuer(BrokerAdapterGateway(_registry()))


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


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )


def _request():
    return ExecutionRequest("EURUSD", Signal.COMPRA, 1.0, 60, ExecutionMode.REAL, request_id="req-1")


def test_direct_active_authorization_cannot_be_manufactured():
    with pytest.raises(PermissionError, match="autoridade REAL"):
        RealExecutionAuthorization(
            "auth", "audit", "fake", "fake-adapter", "req", "EURUSD", True, True
        )


def test_issuer_derives_adapter_identity_from_registry():
    auth = _issuer().issue_authorization(
        authorization_id="auth-1", release_audit=_release_audit(), broker="fake",
        request=_request(), explicit_real_enablement=True,
    )
    assert auth.active
    assert auth.adapter_id == "fake-adapter"


def test_issuer_rejects_missing_explicit_real_enablement():
    with pytest.raises(PermissionError):
        _issuer().issue_authorization(
            authorization_id="auth-1", release_audit=_release_audit(), broker="fake",
            request=_request(), explicit_real_enablement=False,
        )


def test_issuer_rejects_unverified_audit():
    with pytest.raises(PermissionError):
        _issuer().issue_authorization(
            authorization_id="auth-1", release_audit=object(), broker="fake",
            request=_request(), explicit_real_enablement=True,
        )


def test_admission_issuer_derives_all_operation_identity_from_authorization():
    issuer = _issuer()
    auth = issuer.issue_authorization(
        authorization_id="auth-1", release_audit=_release_audit(), broker="fake",
        request=_request(), explicit_real_enablement=True,
    )
    admission = issuer.issue_admission(
        admission_id="adm-1", authorization=auth,
        release_audit=_release_audit(), safety=_safety(), broker_available=True,
    )
    assert admission.admitted
    assert admission.audit_id == auth.audit_id
    assert admission.broker_id == auth.broker_id
    assert admission.adapter_id == auth.adapter_id
    assert admission.request_id == auth.request_id
    assert admission.symbol == auth.symbol


def test_admission_issuer_rejects_forged_or_inactive_authorization():
    with pytest.raises(PermissionError):
        _issuer().issue_admission(
            admission_id="adm", authorization=object(),
            release_audit=_release_audit(), safety=_safety(), broker_available=True,
        )


def test_admission_issuer_rejects_unready_safety():
    issuer = _issuer()
    audit = _release_audit()
    auth = issuer.issue_authorization(
        authorization_id="auth-1", release_audit=audit, broker="fake",
        request=_request(), explicit_real_enablement=True,
    )
    unsafe = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=False, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    with pytest.raises(PermissionError):
        issuer.issue_admission(
            admission_id="adm-1", authorization=auth,
            release_audit=audit, safety=unsafe, broker_available=True,
        )


def test_direct_admitted_value_cannot_be_manufactured():
    from core.p117_real_admission import RealAdmission, RealAdmissionStatus
    with pytest.raises(PermissionError, match="autoridade REAL"):
        RealAdmission(
            "adm", "audit", RealAdmissionStatus.ADMITTED,
            "fake", "fake-adapter", "req", "EURUSD", (),
        )
