"""Tenant-only assistant context assembly.

This excludes shared runtime status, risk, statistics and decision memory.
Remote chat remains gated until trusted identity and request wiring validate.
"""
from __future__ import annotations

from typing import Any

from assistant.read_only_context import collect_read_only_context
from finance.tenant_fiscal_store import TenantFiscalStoreFactory
from security.tenant_context import TenantContext


class _UnavailableSharedContext:
    """Neutral adapter preventing calls into shared EcosystemService state."""

    @staticmethod
    def system_status() -> dict[str, Any]:
        return {}

    @staticmethod
    def risk_status() -> dict[str, Any]:
        return {}

    @staticmethod
    def operational_observability() -> dict[str, Any]:
        return {}

    @staticmethod
    def statistics() -> dict[str, Any]:
        return {}

    @staticmethod
    def memory_view(limit: int = 5) -> list[dict[str, Any]]:
        return []


def collect_tenant_fiscal_context(
    factory: TenantFiscalStoreFactory,
    tenant_context: TenantContext,
) -> dict[str, Any]:
    """Build fiscal context by resolving repositories from a tenant context.

    Repositories are never accepted from the caller. The factory derives the
    storage shard from the immutable TenantContext, which must have been
    created at the trusted server-side identity boundary.
    """
    if not isinstance(factory, TenantFiscalStoreFactory):
        raise TypeError("fábrica fiscal isolada é obrigatória")
    if not isinstance(tenant_context, TenantContext):
        raise TypeError("TenantContext confiável é obrigatório")

    repositories = factory.get(tenant_context)
    context = collect_read_only_context(
        _UnavailableSharedContext(),
        repositories.reserve,
        repositories.owner_id,
        repositories.foreign_pending,
        repositories.domestic_pending,
    )
    # Reuse existing fiscal sanitizers, but discard synthetic shared sections.
    return {
        "scope": "TENANT_AND_SUBJECT",
        "operational_context": "NOT_INCLUDED_SHARED_STATE",
        "as_of": context["as_of"],
        "sources": [
            "tenant_fiscal_reserve",
            "tenant_foreign_pending_queue_summary",
            "tenant_domestic_pending_queue_summary",
            "fiscal_classification_catalog",
        ],
        "fiscal_reserve": context["fiscal_reserve"],
        "fiscal_classification_catalog": context["fiscal_classification_catalog"],
        "assistant_safety": context["assistant_safety"],
    }
