from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import FrozenSet, Mapping


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
        if not isinstance(self.subject_id, str) or not self.subject_id.strip():
            raise ValueError("subject_id is required")
        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not isinstance(self.role, SaaSRole):
            raise ValueError("role is invalid")


@dataclass(frozen=True)
class PlanDefinition:
    """Provider-neutral authorization plan; pricing and billing stay outside core.

    Plans grant capabilities through entitlements. They do not impose arbitrary
    product-capacity counters; infrastructure protections and trading-risk controls
    are enforced by their own boundaries.
    """

    name: str
    entitlements: FrozenSet[Entitlement] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("plan name is required")
        object.__setattr__(self, "entitlements", frozenset(self.entitlements))

    def allows(self, entitlement: Entitlement) -> bool:
        return entitlement in self.entitlements


@dataclass(frozen=True)
class SaaSAuthorizationPolicy:
    """Fail-closed authorization boundary for tenant-scoped product features."""

    role_entitlements: Mapping[SaaSRole, FrozenSet[Entitlement]] = field(
        default_factory=lambda: MappingProxyType(
            {
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
    )

    def __post_init__(self) -> None:
        normalized: dict[SaaSRole, FrozenSet[Entitlement]] = {}
        for role, entitlements in self.role_entitlements.items():
            if not isinstance(role, SaaSRole):
                raise ValueError("role entitlement key is invalid")
            normalized[role] = frozenset(entitlements)
        object.__setattr__(self, "role_entitlements", MappingProxyType(normalized))

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
