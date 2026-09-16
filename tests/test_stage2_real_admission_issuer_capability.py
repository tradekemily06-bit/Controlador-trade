import ast
from pathlib import Path

import pytest

from core.models import Signal
from core.p111_pre_real_audit import PreRealAuditBoundary
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.p117_real_admission import RealAdmissionBoundary, RealAdmissionStatus
from core.real_privilege_issuer import RealPrivilegeIssuer
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.ports import ExecutionMode, ExecutionRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_ISSUER = "core/real_privilege_issuer.py"


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


def _issuer():
    registry = BrokerRegistry()
    adapter = type("Adapter", (), {
        "is_available": lambda self: True,
        "execute": lambda self, request: None,
    })()
    registry.register("fake", adapter, adapter_id="fake-adapter")
    return RealPrivilegeIssuer(BrokerAdapterGateway(registry))


def _authorization():
    issuer = _issuer()
    request = ExecutionRequest("TEST", Signal.COMPRA, 1.0, 60, ExecutionMode.REAL, request_id="req")
    return issuer.issue_authorization(
        authorization_id="auth", release_audit=_release_audit(), broker="fake",
        request=request, explicit_real_enablement=True,
    )


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )


def test_internal_admission_issue_requires_exact_private_capability():
    boundary = RealAdmissionBoundary()
    authorization = _authorization()
    kwargs = dict(
        admission_id="adm", audit_id="a116", audit_verified=True,
        authorization=authorization, safety_ready=True, broker_available=True,
    )
    with pytest.raises(PermissionError):
        boundary._issue(**kwargs)
    with pytest.raises(PermissionError):
        boundary._issue(**kwargs, issuer_capability=object())


def test_only_authoritative_issuer_can_produce_admitted_state():
    issuer = _issuer()
    admission = issuer.issue_admission(
        admission_id="adm", authorization=_authorization(),
        release_audit=_release_audit(), safety=_safety(), broker_available=True,
    )
    assert admission.status is RealAdmissionStatus.ADMITTED
    assert admission.admitted
    assert admission.issuer_valid


def test_public_legacy_boundary_stays_blocked_even_when_inputs_are_green():
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="a116", audit_verified=True,
        authorization_active=True, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="fake-adapter", request_id="req", symbol="TEST",
    )
    assert admission.status is RealAdmissionStatus.BLOCKED
    assert not admission.admitted


def test_production_has_no_other_admission_issue_call_site():
    roots = [REPO_ROOT / name for name in ("app.py", "core", "execution", "integration", "security")]
    violations = []
    for root in roots:
        paths = [root] if root.is_file() else list(root.rglob("*.py"))
        for path in paths:
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative.startswith("tests/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                owner = node.func.value
                if isinstance(owner, ast.Attribute) and owner.attr == "_admission_boundary" and node.func.attr == "_issue":
                    if relative != AUTHORIZED_ISSUER:
                        violations.append(f"{relative}:{node.lineno}")
    assert violations == []


def test_admission_identity_is_bound_to_authorization():
    authorization = _authorization()
    issuer = _issuer()
    admission = issuer.issue_admission(
        admission_id="adm", authorization=authorization,
        release_audit=_release_audit(), safety=_safety(), broker_available=True,
    )
    assert admission.broker_id == authorization.broker_id
    assert admission.adapter_id == authorization.adapter_id
    assert admission.request_id == authorization.request_id
    assert admission.symbol == authorization.symbol
    assert admission.audit_id == authorization.audit_id


def test_authorization_active_state_still_requires_its_own_issuer_proof():
    with pytest.raises(PermissionError):
        RealExecutionAuthorization(
            "auth", "a116", "fake", "fake-adapter", "req", "TEST", True, True,
        )
