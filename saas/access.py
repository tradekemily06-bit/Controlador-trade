from __future__ import annotations

from dataclasses import dataclass

from .contracts import Entitlement, PlanDefinition, SaaSAuthorizationPolicy, TenantContext


@dataclass(frozen=True)
class SaaSAccessDecision:
    allowed: bool
    reason: str


class SaaSAccessController:
    """Provider-neutral runtime gate for tenant-scoped product capabilities.

    Authentication, sessions, billing, persistence, and identity-provider integration
    stay outside this layer. A missing tenant context always fails closed.
    """

    def __init__(self, policy: SaaSAuthorizationPolicy | None = None) -> None:
        self.policy = policy or SaaSAuthorizationPolicy()

    def authorize(
        self,
        context: TenantContext | None,
        entitlement: Entitlement,
        plan: PlanDefinition,
    ) -> SaaSAccessDecision:
        if context is None:
            return SaaSAccessDecision(False, "tenant_identity_required")
        if not self.policy.authorize(context, entitlement, plan):
            return SaaSAccessDecision(False, "entitlement_denied")
        return SaaSAccessDecision(True, "authorized")

    def within_limit(self, plan: PlanDefinition, resource: str, current_usage: int) -> SaaSAccessDecision:
        if current_usage < 0:
            return SaaSAccessDecision(False, "invalid_usage")
        limit = plan.limit_for(resource)
        if limit is None:
            return SaaSAccessDecision(True, "unlimited")
        if limit < 0:
            return SaaSAccessDecision(False, "invalid_plan_limit")
        if current_usage >= limit:
            return SaaSAccessDecision(False, "plan_limit_reached")
        return SaaSAccessDecision(True, "within_limit")
