from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet


class SaaSRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class Entitlement(str, Enum):
    ANALYSIS = "analysis"
    REPLAY = "replay"
    MEMORY = "memory"
    STATISTICS = "statistics"
    NEWS = "news"
    BROKER_CONNECTIONS = "broker_connections"
    EXECUTION = "execution"


@dataclass(frozen=True)
class TenantContext:
    """Authenticated SaaS scope supplied by the deployment identity layer."""

    subject_id: str
    tenant_id: str
    role: SaaSRole = SaaSRole.MEMBER

    def validate(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id is required")
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")


@dataclass(frozen=True)
class PlanDefinition:
    """Provider-neutral plan contract; pricing and billing stay outside core."""

    name: str
    entitlements: FrozenSet[Entitlement] = field(default_factory=frozenset)
    limits: dict[str, int | None] = field(default_factory=dict)

    def allows(self, entitlement: Entitlement) -> bool:
        return entitlement in self.entitlements

    def limit_for(self, resource: str) -> int | None:
        return self.limits.get(resource)


@dataclass(frozen=True)
class SaaSAuthorizationPolicy:
    """Fail-closed authorization boundary for tenant-scoped product features."""

    role_entitlements: dict[SaaSRole, FrozenSet[Entitlement]] = field(
        default_factory=lambda: {
            SaaSRole.OWNER: frozenset(Entitlement),
            SaaSRole.ADMIN: frozenset(
                {
                    Entitlement.ANALYSIS,
                    Entitlement.REPLAY,
                    Entitlement.MEMORY,
                    Entitlement.STATISTICS,
                    Entitlement.NEWS,
                    Entitlement.BROKER_CONNECTIONS,
                }
            ),
            SaaSRole.MEMBER: frozenset(
                {
                    Entitlement.ANALYSIS,
                    Entitlement.REPLAY,
                    Entitlement.MEMORY,
                    Entitlement.STATISTICS,
                    Entitlement.NEWS,
                }
            ),
            SaaSRole.VIEWER: frozenset(
                {Entitlement.ANALYSIS, Entitlement.MEMORY, Entitlement.STATISTICS, Entitlement.NEWS}
            ),
        }
    )

    def authorize(
        self,
        context: TenantContext | None,
        entitlement: Entitlement,
        plan: PlanDefinition,
    ) -> bool:
        if context is None:
            return False
        try:
            context.validate()
        except ValueError:
            return False
        return entitlement in self.role_entitlements.get(context.role, frozenset()) and plan.allows(entitlement)
