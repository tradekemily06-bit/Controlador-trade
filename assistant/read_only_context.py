"""Read-only context assembly for the Controlador Trading assistant.

This module deliberately exposes only approved summaries from existing services.
It does not execute trades, change settings, move funds, or infer tax outcomes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def collect_read_only_context(service: Any, fiscal_reserve: Any) -> dict[str, Any]:
    """Build a compact, factual snapshot for an assistant response.

    The caller is responsible for authenticating the user and deciding whether
    the snapshot may be sent to an external model provider.
    """
    if service is None or fiscal_reserve is None:
        raise ValueError("serviço do ecossistema e Reserva Fiscal são obrigatórios")

    status = service.system_status()
    risk = service.risk_status()
    observability = service.operational_observability()
    statistics = service.statistics()
    fiscal = fiscal_reserve.summary()
    recent_decisions = service.memory_view(limit=5)

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "sources": [
            "system_status",
            "risk_status",
            "operational_observability",
            "statistics",
            "fiscal_reserve",
            "recent_decisions",
        ],
        "system": {
            "mode": status.get("mode", "UNKNOWN"),
            "execution_allowed": bool(status.get("execution_allowed", False)),
            "real": status.get("real", "UNKNOWN"),
            "health": status.get("health", "UNKNOWN"),
            "components": status.get("components", {}),
        },
        "risk": risk,
        "operations": observability,
        "statistics": statistics,
        "fiscal_reserve": fiscal,
        "recent_decisions": recent_decisions,
        "assistant_safety": {
            "read_only": True,
            "may_execute_orders": False,
            "may_enable_real": False,
            "may_move_money": False,
            "tax_estimates_are_not_tax_assessments": True,
            "unknown_data_must_be_reported_as_unavailable": True,
        },
    }
