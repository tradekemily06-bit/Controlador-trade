"""Stable serialization for the broker-agnostic Controlador-trade API result."""
from __future__ import annotations

from typing import Any

from analysis.decision_record import DecisionRecord
from .models import AnalysisResult, Signal
from .primary_result_view import PrimaryResultView, build_primary_result_view


def serialize_primary_result(result: AnalysisResult) -> dict[str, Any]:
    """Serialize an analysis result for the future web/mobile API.

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


def serialize_decision_record(record: DecisionRecord) -> dict[str, Any]:
    """Expose the stable result contract while preserving API decision metadata."""
    result = AnalysisResult(
        signal=Signal(record.signal),
        score=record.score,
        reason=record.reason,
        confirmed=record.confirmed,
        symbol=record.symbol,
        timeframe=record.timeframe,
    )
    return serialize_primary_result(result)
