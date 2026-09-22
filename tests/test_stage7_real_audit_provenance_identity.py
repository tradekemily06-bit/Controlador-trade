import pytest

from core.p112_real_execution_contract import RealExecutionAuthorization, _issue_real_authorization
from core.p116_real_release_audit import RealReleaseAudit, RealReleaseAuditBoundary, ReleaseAuditStatus
from core.real_authorization_issuer import RealAuthorizationIssuer


def test_field_identical_verified_audit_copy_cannot_be_used_for_real_authorization():
    genuine = RealReleaseAuditBoundary().audit(
        audit_id="same-audit",
        pre_real_verified=True,
        shadow_passed=True,
        safety_ready=True,
        broker_boundary_ready=True,
        explicit_real_contract=True,
    )
    forged_copy = RealReleaseAudit(
        genuine.audit_id,
        genuine.status,
        genuine.prerequisites,
        genuine.reasons,
    )

    assert genuine.verified
    assert forged_copy == genuine
    assert forged_copy is not genuine

    try:
        RealAuthorizationIssuer().issue(
            audit=forged_copy,
            authorization_id="auth",
            audit_id="same-audit",
            broker_id="broker",
            adapter_id="adapter",
            request_id="request",
            symbol="TEST",
            explicit_approval=True,
        )
    except ValueError as exc:
        assert "fronteira" in str(exc)
    else:
        raise AssertionError("field-identical fabricated audit must never issue REAL authorization")


def test_blocked_audit_is_never_registered_as_verified():
    blocked = RealReleaseAuditBoundary().audit(
        audit_id="blocked-audit",
        pre_real_verified=True,
        shadow_passed=False,
        safety_ready=True,
        broker_boundary_ready=True,
        explicit_real_contract=True,
    )
    assert blocked.status is ReleaseAuditStatus.BLOCKED
    assert not blocked.verified

    try:
        RealAuthorizationIssuer().issue(
            audit=blocked,
            authorization_id="auth",
            audit_id="blocked-audit",
            broker_id="broker",
            adapter_id="adapter",
            request_id="request",
            symbol="TEST",
            explicit_approval=True,
        )
    except ValueError as exc:
        assert "fronteira" in str(exc)
    else:
        raise AssertionError("blocked audit must never issue REAL authorization")


def test_field_identical_active_authorization_without_issuer_provenance_is_inactive():
    forged = RealExecutionAuthorization(
        "auth", "audit", "broker", "adapter", "request", "TEST", True, True
    )
    assert not forged.active


def test_issuer_provenance_makes_authorization_active():
    audit = RealReleaseAuditBoundary().audit(
        audit_id="issued-audit",
        pre_real_verified=True,
        shadow_passed=True,
        safety_ready=True,
        broker_boundary_ready=True,
        explicit_real_contract=True,
    )
    authorization = RealAuthorizationIssuer().issue(
        audit=audit,
        authorization_id="issued-auth",
        audit_id="issued-audit",
        broker_id="broker",
        adapter_id="adapter",
        request_id="request",
        symbol="TEST",
        explicit_approval=True,
    )
    assert authorization.active


def test_low_level_authorization_factory_rejects_missing_issuer_capability():
    with pytest.raises(TypeError):
        _issue_real_authorization(
            authorization_id="auth",
            audit_id="audit",
            broker_id="broker",
            adapter_id="adapter",
            request_id="request",
            symbol="TEST",
        )


def test_low_level_authorization_factory_rejects_forged_capability():
    with pytest.raises(PermissionError):
        _issue_real_authorization(
            authorization_id="auth",
            audit_id="audit",
            broker_id="broker",
            adapter_id="adapter",
            request_id="request",
            symbol="TEST",
            issuer_capability=object(),
        )
