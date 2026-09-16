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
