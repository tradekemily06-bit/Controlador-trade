import ast
import copy
import dataclasses
import json
import pickle
from pathlib import Path

import pytest

from core.models import Signal
from core.p111_pre_real_audit import PreRealAuditBoundary
from core.p114_real_safety_gate import RealSafetyGate
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.p117_real_admission import RealAdmissionStatus, RealAdmissionBoundary
from core.p112_real_execution_contract import (
    RealExecutionAuthorization,
    _REAL_AUTHORIZATION_ISSUER_CAPABILITY,
)
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
    adapter = type("Adapter", (), {
        "is_available": lambda self: True,
        "execute": lambda self, request: None,
    })()
    registry.register("fake", adapter, adapter_id="fake-adapter")
    return registry


def _active_authorization():
    gateway = BrokerAdapterGateway(_registry())
    request = ExecutionRequest("TEST", Signal.COMPRA, 1.0, 60, ExecutionMode.REAL, request_id="req")
    return RealPrivilegeIssuer(gateway).issue_authorization(
        authorization_id="auth", release_audit=_release_audit(), broker="fake",
        request=request, explicit_real_enablement=True,
    )


def _admitted():
    authorization = _active_authorization()
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    return RealPrivilegeIssuer(BrokerAdapterGateway(_registry())).issue_admission(
        admission_id="adm", authorization=authorization,
        release_audit=_release_audit(), safety=safety, broker_available=True,
    )


def test_active_real_authorization_cannot_be_constructed_directly():
    with pytest.raises(PermissionError):
        RealExecutionAuthorization("auth", "audit", "fake", "fake-adapter", "req", "TEST", True, True)


def test_real_authorization_factory_requires_private_capability():
    kwargs = dict(
        authorization_id="auth", audit_id="audit", broker_id="fake",
        adapter_id="fake-adapter", request_id="req", symbol="TEST",
    )
    with pytest.raises(PermissionError):
        RealExecutionAuthorization._issue(**kwargs, issuer_capability=None)
    with pytest.raises(PermissionError):
        RealExecutionAuthorization._issue(**kwargs, issuer_capability=object())
    issued = RealExecutionAuthorization._issue(
        **kwargs, issuer_capability=_REAL_AUTHORIZATION_ISSUER_CAPABILITY,
    )
    assert issued.active and issued.issuer_valid


def test_legacy_public_admission_cannot_create_admitted_state():
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="fake-adapter", request_id="req", symbol="TEST",
    )
    assert admission.status is RealAdmissionStatus.BLOCKED
    assert not admission.admitted


def test_authoritative_issuer_derives_adapter_and_operation_identity():
    authorization = _active_authorization()
    assert authorization.active and authorization.issuer_valid
    assert (authorization.request_id, authorization.symbol) == ("req", "TEST")
    assert (authorization.broker_id, authorization.adapter_id) == ("fake", "fake-adapter")


def test_active_authorization_cannot_be_rebound_with_dataclass_replace():
    with pytest.raises(PermissionError):
        dataclasses.replace(_active_authorization(), symbol="XAUUSD")


def test_admitted_privilege_cannot_be_rebound_with_dataclass_replace():
    admission = _admitted()
    assert admission.admitted
    with pytest.raises(PermissionError):
        dataclasses.replace(admission, symbol="XAUUSD")


def test_copy_of_exact_immutable_privilege_does_not_change_identity():
    authorization = _active_authorization()
    copied = copy.copy(authorization)
    assert copied.active and copied.issuer_valid
    assert copied == authorization


def test_deepcopy_reconstruction_cannot_restore_active_authorization():
    authorization = _active_authorization()
    restored = copy.deepcopy(authorization)
    assert not restored.active
    assert not restored.issuer_valid


def test_pickle_reconstruction_cannot_restore_active_authorization():
    restored = pickle.loads(pickle.dumps(_active_authorization()))
    assert not restored.active
    assert not restored.issuer_valid


def test_pickle_reconstruction_cannot_restore_admitted_privilege():
    restored = pickle.loads(pickle.dumps(_admitted()))
    assert not restored.admitted
    assert not restored.issuer_valid


def test_json_field_reconstruction_cannot_restore_active_authorization():
    authorization = _active_authorization()
    payload = json.loads(json.dumps({
        "authorization_id": authorization.authorization_id,
        "audit_id": authorization.audit_id,
        "broker_id": authorization.broker_id,
        "adapter_id": authorization.adapter_id,
        "request_id": authorization.request_id,
        "symbol": authorization.symbol,
        "explicitly_enabled": True,
        "real_execution_allowed": True,
    }))
    with pytest.raises(PermissionError):
        RealExecutionAuthorization(**payload)


def test_json_field_reconstruction_cannot_restore_admitted_privilege():
    admission = _admitted()
    payload = {
        "admission_id": admission.admission_id,
        "audit_id": admission.audit_id,
        "status": admission.status,
        "broker_id": admission.broker_id,
        "adapter_id": admission.adapter_id,
        "request_id": admission.request_id,
        "symbol": admission.symbol,
        "reasons": admission.reasons,
    }
    with pytest.raises(Exception):
        type(admission)(**payload)


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
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "RealExecutionAuthorization" and node.func.attr == "_issue":
                        if relative != AUTHORIZED_ISSUER:
                            violations.append(f"{relative}:{node.lineno}: unauthorized authorization issuance")
    assert violations == []


def test_legacy_public_admission_is_not_used_by_production_sources():
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
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "admit":
                    if isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Name) and node.func.value.func.id == "RealAdmissionBoundary":
                        violations.append(f"{relative}:{node.lineno}: legacy REAL admission path")
    assert violations == []
