from saas.access import SaaSAccessController
from saas.contracts import Entitlement, PlanDefinition, SaaSRole, TenantContext


def test_access_requires_tenant_identity():
    plan = PlanDefinition("analysis", frozenset({Entitlement.ANALYSIS}))
    decision = SaaSAccessController().authorize(None, Entitlement.ANALYSIS, plan)
    assert not decision.allowed
    assert decision.reason == "tenant_identity_required"


def test_access_requires_role_and_plan_entitlement():
    controller = SaaSAccessController()
    context = TenantContext("user-1", "tenant-1", SaaSRole.MEMBER)
    plan = PlanDefinition("analysis", frozenset({Entitlement.ANALYSIS}))

    allowed = controller.authorize(context, Entitlement.ANALYSIS, plan)
    denied = controller.authorize(context, Entitlement.BROKER_CONNECTIONS, plan)

    assert allowed.allowed
    assert denied.reason == "entitlement_denied"


def test_plan_limit_is_fail_closed_at_boundary():
    controller = SaaSAccessController()
    plan = PlanDefinition("limited", frozenset({Entitlement.ANALYSIS}), {"analyses": 3})

    assert controller.within_limit(plan, "analyses", 2).allowed
    assert not controller.within_limit(plan, "analyses", 3).allowed
    assert not controller.within_limit(plan, "analyses", -1).allowed


def test_none_limit_is_unlimited():
    plan = PlanDefinition("unlimited", frozenset({Entitlement.ANALYSIS}))
    decision = SaaSAccessController().within_limit(plan, "analyses", 1000000)
    assert decision.allowed
    assert decision.reason == "unlimited"
