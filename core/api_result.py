"""Stable serialization for the broker-agnostic Controlador-trade API result."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .primary_result_view import PrimaryResultView, build_primary_result_view
from .models import AnalysisResult


def serialize_primary_result(result: AnalysisResult) -> dict[str, Any]:
    """Serialize an analysis result for a future web/mobile API.

    The trading decision remains owned by the core models; this function only
    exposes a stable presentation payload. REAL execution is never enabled by
    serialization.
    """
    view: PrimaryResultView = build_primary_result_view(result)
    return {
        "signal": result.signal.value,
        "score": result.score,
        "reason": result.reason,
        "confirmed": result.confirmed,
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "presentation": {
            "status": view.primary.status.value,
            "label": view.primary.label,
            "color": view.primary.color,
            "priority": view.primary.priority,
        },
        "security": {
            "real_blocked": True,
            "label": view.real_security.label,
            "discreet": view.real_security.discreet,
        },
    }
