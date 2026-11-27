"""Tenant-only assistant context assembly.

This excludes shared runtime status, risk, statistics and decision memory.
Remote chat remains gated until trusted identity and request wiring validate.
"""
from __future__ import annotations

from typing import Any

from assistant.read_only_context import collect_read_only_context


class _UnavailableSharedContext:
    """Neutral adapter preventing calls into shared EcosystemService state."""

    @staticmethod
    def system_status() -> dict[str, Any]: return {}
    @staticmethod
    def risk_status() -> dict[str, Any]: return {}
    @staticmethod
    def operational_observability() -> dict[str, Any]: return {}
    @staticmethod
    def statistics() -> dict[str, Any]: return {}
    @staticmethod
    def memory_view(limit: int = 5) -> list[dict[str, Any]]: return []


def collect_tenant_fiscal_context(repositories: Any) -> dict[str, Any]:
    """Build sanitized fiscal context from one tenant repository bundle only.

    The bundle must come from TenantFiscalStoreFactory.get() with a
    TenantContext established by trusted server-side identity middleware.
    No shared EcosystemService is accepted or consulted.
    """
    required = ("owner_id", "reserve", "foreign_pending", "domestic_pending")
    if any(not hasattr(repositories, field) for field in required):
        raise TypeError("repositórios fiscais isolados são obrigatórios")

    context = collect_read_only_context(
        _UnavailableSharedContext(), repositories.reserve, repositories.owner_id,
        repositories.foreign_pending, repositories.domestic_pending,
    )
    # Reuse existing fiscal sanitizers, but discard synthetic shared sections.
    return {
        "scope": "TENANT_AND_SUBJECT",
        "operational_context": "NOT_INCLUDED_SHARED_STATE",
        "as_of": context["as_of"],
        "sources": [
            "tenant_fiscal_reserve", "tenant_foreign_pending_queue_summary",
            "tenant_domestic_pending_queue_summary", "fiscal_classification_catalog",
        ],
        "fiscal_reserve": context["fiscal_reserve"],
        "fiscal_classification_catalog": context["fiscal_classification_catalog"],
        "assistant_safety": context["assistant_safety"],
    }
