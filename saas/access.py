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

    Product capacity is not restricted by plan counters. Plans describe authorization
    entitlements only; infrastructure protections and trading-risk controls remain
    separate concerns.
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
