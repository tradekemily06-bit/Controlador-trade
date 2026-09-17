from __future__ import annotations

from dataclasses import replace
import pickle

import pytest

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p116_real_release_audit import RealReleaseAudit, ReleaseAuditStatus
from core.p117_real_admission import RealAdmission, RealAdmissionBoundary, RealAdmissionStatus
from core.real_privilege_issuer import RealPrivilegeIssuer
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal


class FakeAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        raise AssertionError("test adapter must not be dispatched")


def _audit() -> RealReleaseAudit:
    return RealReleaseAudit("release-1", ReleaseAuditStatus.VERIFIED, ("P111",), ())


def _request(request_id="req-1", symbol="EURUSD") -> ExecutionRequest:
    return ExecutionRequest(symbol, Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id=request_id,
                            risk_state_fingerprint="risk-fingerprint")


def _issuer():
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter(), adapter_id="fake-adapter")
    return RealPrivilegeIssuer(BrokerAdapterGateway(registry))


def _issued_authorization():
    return _issuer().issue_authorization(
        authorization_id="auth-1", release_audit=_audit(), broker="fake",
        request=_request(), explicit_real_enablement=True,
    )


def test_direct_active_authorization_is_rejected():
    with pytest.raises(PermissionError):
        RealExecutionAuthorization("auth", "audit", "fake", "fake-adapter", "req", "EURUSD", True, True)


def test_issuer_derives_identity_from_request_and_registry():
    authorization = _issued_authorization()
    assert authorization.active
    assert authorization.issuer_valid
    assert authorization.request_id == "req-1"
    assert authorization.symbol == "EURUSD"
    assert authorization.adapter_id == "fake-adapter"


def test_issued_authorization_cannot_be_rebound_with_dataclasses_replace():
    authorization = _issued_authorization()
    with pytest.raises(PermissionError):
        replace(authorization, symbol="XAUUSD")


def test_legacy_reconstruction_cannot_create_active_authorization():
    with pytest.raises(PermissionError):
        RealExecutionAuthorization(
            "auth", "audit", "fake", "fake-adapter", "req", "EURUSD", True, True,
        )


def test_pickle_reconstruction_of_authorization_fails_closed():
    restored = pickle.loads(pickle.dumps(_issued_authorization()))
    assert not restored.active
    assert not restored.issuer_valid


def test_direct_admitted_object_is_rejected():
    with pytest.raises(PermissionError):
        RealAdmission(
            "adm", "release-1", RealAdmissionStatus.ADMITTED,
            "fake", "fake-adapter", "req-1", "EURUSD", (),
        )


def test_legacy_admission_boundary_cannot_manufacture_admitted_privilege():
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="release-1", audit_verified=True,
        authorization_active=True, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="fake-adapter", request_id="req-1", symbol="EURUSD",
    )
    assert admission.status is RealAdmissionStatus.BLOCKED
    assert not admission.admitted


def test_issuer_derives_admission_identity_from_authorization():
    issuer = _issuer()
    authorization = issuer.issue_authorization(
        authorization_id="auth-1", release_audit=_audit(), broker="fake",
        request=_request(), explicit_real_enablement=True,
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    admission = issuer.issue_admission(
        admission_id="adm-1", authorization=authorization,
        release_audit=_audit(), safety=safety, broker_available=True,
    )
    assert admission.admitted
    assert admission.issuer_valid
    assert admission.request_id == authorization.request_id
    assert admission.symbol == authorization.symbol
    assert admission.adapter_id == authorization.adapter_id


def test_issued_admission_cannot_be_rebound_with_dataclasses_replace():
    issuer = _issuer()
    authorization = issuer.issue_authorization(
        authorization_id="auth-1", release_audit=_audit(), broker="fake",
        request=_request(), explicit_real_enablement=True,
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    admission = issuer.issue_admission(
        admission_id="adm-1", authorization=authorization,
        release_audit=_audit(), safety=safety, broker_available=True,
    )
    with pytest.raises(PermissionError):
        replace(admission, symbol="XAUUSD")


def test_pickle_reconstruction_of_admission_fails_closed():
    issuer = _issuer()
    authorization = issuer.issue_authorization(
        authorization_id="auth-1", release_audit=_audit(), broker="fake",
        request=_request(), explicit_real_enablement=True,
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    admission = issuer.issue_admission(
        admission_id="adm-1", authorization=authorization,
        release_audit=_audit(), safety=safety, broker_available=True,
    )
    restored = pickle.loads(pickle.dumps(admission))
    assert not restored.admitted
    assert not restored.issuer_valid
