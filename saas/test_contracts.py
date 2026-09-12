import pytest

from saas.contracts import (
    Entitlement,
    PlanDefinition,
    SaaSAuthorizationPolicy,
    SaaSRole,
    TenantContext,
)


def test_tenant_context_requires_subject_and_tenant():
    with pytest.raises(ValueError):
        TenantContext(subject_id="", tenant_id="tenant").validate()
    with pytest.raises(ValueError):
        TenantContext(subject_id="user", tenant_id="").validate()


def test_tenant_context_rejects_invalid_role():
    with pytest.raises(ValueError):
        TenantContext("user", "tenant", "OWNER").validate()


def test_authorization_is_tenant_and_role_scoped():
    plan = PlanDefinition(
        name="owner-test",
        entitlements=frozenset({Entitlement.ANALYSIS, Entitlement.BROKER_CONNECTIONS}),
    )
    policy = SaaSAuthorizationPolicy()
    owner = TenantContext("user-1", "tenant-1", SaaSRole.OWNER)
    member = TenantContext("user-2", "tenant-1", SaaSRole.MEMBER)

    assert policy.authorize(owner, Entitlement.ANALYSIS, plan)
    assert not policy.authorize(member, Entitlement.BROKER_CONNECTIONS, plan)


def test_plan_is_an_independent_gate():
    policy = SaaSAuthorizationPolicy()
    owner = TenantContext("user-1", "tenant-1", SaaSRole.OWNER)
    plan = PlanDefinition(name="analysis-only", entitlements=frozenset({Entitlement.ANALYSIS}))

    assert policy.authorize(owner, Entitlement.ANALYSIS, plan)
    assert not policy.authorize(owner, Entitlement.REPLAY, plan)


def test_missing_identity_fails_closed():
    policy = SaaSAuthorizationPolicy()
    plan = PlanDefinition(name="all", entitlements=frozenset(Entitlement))

    assert not policy.authorize(None, Entitlement.ANALYSIS, plan)
    assert not policy.authorize(TenantContext("", "tenant"), Entitlement.ANALYSIS, plan)


def test_plan_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        PlanDefinition(name="", entitlements=frozenset())
    with pytest.raises(ValueError):
        PlanDefinition(name="bad", limits={"analysis": -1})
    with pytest.raises(ValueError):
        PlanDefinition(name="bad", limits={"analysis": True})


def test_plan_limits_and_policy_are_immutable_at_runtime():
    limits = {"analysis": 10}
    plan = PlanDefinition(name="safe", limits=limits)
    limits["analysis"] = 0
    assert plan.limit_for("analysis") == 10

    policy = SaaSAuthorizationPolicy()
    with pytest.raises(TypeError):
        policy.role_entitlements[SaaSRole.MEMBER] = frozenset()
