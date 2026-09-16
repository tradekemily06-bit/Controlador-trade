import pytest

from core.p114_real_safety_gate import RealSafetyGate
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p117_real_admission import RealAdmission, RealAdmissionStatus
from core.real_privilege_issuer import RealPrivilegeIssuer
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry


class FakeAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        raise AssertionError("issuer tests must never dispatch")


def _registry():
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter(), adapter_id="fake-adapter")
    return registry


def _issuer():
    return RealPrivilegeIssuer(BrokerAdapterGateway(_registry()))


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True,
        kill_switch_clear=True,
        market_healthy=True,
        recovery_safe=True,
        risk_approved=True,
        broker_available=True,
    )


def test_direct_active_authorization_cannot_be_manufactured():
    with pytest.raises(PermissionError, match="autoridade REAL"):
        RealExecutionAuthorization(
            "auth", "audit", "fake", "fake-adapter", "req", "EURUSD", True, True
        )


def test_issuer_derives_adapter_identity_from_registry():
    auth = _issuer().issue_authorization(
        authorization_id="auth-1", audit_id="audit-1", request_id="req-1",
        symbol="EURUSD", broker_id="fake", audit_verified=True,
        explicitly_enabled=True, real_execution_allowed=True,
    )
    assert auth.active
    assert auth.adapter_id == "fake-adapter"


def test_issuer_rejects_missing_explicit_real_enablement():
    with pytest.raises(PermissionError):
        _issuer().issue_authorization(
            authorization_id="auth-1", audit_id="audit-1", request_id="req-1",
            symbol="EURUSD", broker_id="fake", audit_verified=True,
            explicitly_enabled=False, real_execution_allowed=True,
        )


def test_issuer_rejects_unverified_audit():
    with pytest.raises(PermissionError):
        _issuer().issue_authorization(
            authorization_id="auth-1", audit_id="audit-1", request_id="req-1",
            symbol="EURUSD", broker_id="fake", audit_verified=False,
            explicitly_enabled=True, real_execution_allowed=True,
        )


def test_admission_issuer_derives_all_operation_identity_from_authorization():
    issuer = _issuer()
    auth = issuer.issue_authorization(
        authorization_id="auth-1", audit_id="audit-1", request_id="req-1",
        symbol="EURUSD", broker_id="fake", audit_verified=True,
        explicitly_enabled=True, real_execution_allowed=True,
    )
    admission = issuer.issue_admission(
        admission_id="adm-1", authorization=auth,
        audit_verified=True, safety=_safety(),
    )
    assert admission.admitted
    assert admission.audit_id == auth.audit_id
    assert admission.broker_id == auth.broker_id
    assert admission.adapter_id == auth.adapter_id
    assert admission.request_id == auth.request_id
    assert admission.symbol == auth.symbol


def test_admission_issuer_rejects_forged_or_inactive_authorization():
    inactive = RealExecutionAuthorization(
        "auth", "audit", "fake", "fake-adapter", "req", "EURUSD", False, False
    )
    with pytest.raises(PermissionError):
        _issuer().issue_admission(
            admission_id="adm", authorization=inactive,
            audit_verified=True, safety=_safety(),
        )


def test_admission_issuer_rejects_unready_safety():
    issuer = _issuer()
    auth = issuer.issue_authorization(
        authorization_id="auth-1", audit_id="audit-1", request_id="req-1",
        symbol="EURUSD", broker_id="fake", audit_verified=True,
        explicitly_enabled=True, real_execution_allowed=True,
    )
    unsafe = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=False,
        market_healthy=True, recovery_safe=True,
        risk_approved=True, broker_available=True,
    )
    with pytest.raises(PermissionError):
        issuer.issue_admission(
            admission_id="adm-1", authorization=auth,
            audit_verified=True, safety=unsafe,
        )


def test_direct_admitted_value_cannot_be_manufactured():
    with pytest.raises(PermissionError, match="autoridade REAL"):
        RealAdmission(
            "adm", "audit", RealAdmissionStatus.ADMITTED,
            "fake", "fake-adapter", "req", "EURUSD", (),
        )
