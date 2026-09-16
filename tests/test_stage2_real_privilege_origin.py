import ast
from pathlib import Path

import pytest

from core.p111_pre_real_audit import PreRealAuditBoundary
from core.p114_real_safety_gate import RealSafetyGate
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.p117_real_admission import RealAdmissionStatus, RealAdmissionBoundary
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.real_privilege_issuer import RealPrivilegeIssuer
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.ports import ExecutionMode, ExecutionRequest


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_ISSUER = "core/real_privilege_issuer.py"
AUTHORIZED_AUTH_MODULE = "core/p112_real_execution_contract.py"
AUTHORIZED_ADMISSION_MODULE = "core/p117_real_admission.py"


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


def _registry():
    registry = BrokerRegistry()
    registry.register("fake", type("Adapter", (), {"is_available": lambda self: True, "execute": lambda self, request: None})(), adapter_id="fake-adapter")
    return registry


def test_active_real_authorization_cannot_be_constructed_directly():
    with pytest.raises(PermissionError):
        RealExecutionAuthorization("auth", "audit", "fake", "fake-adapter", "req", "TEST", True, True)


def test_legacy_public_admission_cannot_create_admitted_state():
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="fake-adapter", request_id="req", symbol="TEST",
    )
    assert admission.status is RealAdmissionStatus.BLOCKED


def test_authoritative_issuer_derives_adapter_and_operation_identity():
    registry = _registry()
    gateway = BrokerAdapterGateway(registry)
    issuer = RealPrivilegeIssuer(gateway)
    request = ExecutionRequest("TEST", "COMPRA", 1.0, 60, ExecutionMode.REAL, request_id="req")
    authorization = issuer.issue_authorization(
        authorization_id="auth", release_audit=_release_audit(), broker="fake",
        request=request, explicit_real_enablement=True,
    )
    assert authorization.active
    assert authorization.request_id == request.request_id
    assert authorization.symbol == request.symbol
    assert authorization.broker_id == "fake"
    assert authorization.adapter_id == "fake-adapter"


def test_production_sources_have_single_active_real_privilege_origin():
    production_roots = [REPO_ROOT / name for name in ("app.py", "core", "execution", "integration", "security")]
    violations = []
    for root in production_roots:
        paths = [root] if root.is_file() else list(root.rglob("*.py"))
        for path in paths:
            relative = path.relative_to(REPO_ROOT).as_posix()
            if "/test" in relative or relative.startswith("tests/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == "RealExecutionAuthorization" and relative != AUTHORIZED_AUTH_MODULE:
                        violations.append(f"{relative}:{node.lineno}: direct authorization constructor")
                    if node.func.id == "RealAdmission" and relative != AUTHORIZED_ADMISSION_MODULE:
                        violations.append(f"{relative}:{node.lineno}: direct admission constructor")
    assert violations == []


def test_only_authorized_issuer_uses_active_authorization_factory():
    issuer_path = REPO_ROOT / AUTHORIZED_ISSUER
    tree = ast.parse(issuer_path.read_text(encoding="utf-8"), filename=AUTHORIZED_ISSUER)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "RealExecutionAuthorization"
        and node.func.attr == "_issue"
    ]
    assert len(calls) == 1
