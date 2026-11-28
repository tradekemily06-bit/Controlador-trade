"""Evidence gate for explainable market recommendations.

This module deliberately does not manufacture a probability of profit or a
confidence percentage. It checks whether the evidence needed to publish a
directional recommendation is present and sufficiently trustworthy.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


_ALLOWED_SIGNALS = {"COMPRA", "VENDA", "AGUARDAR"}
_ALLOWED_COST_STATES = {"NET_VERIFIED", "INCOMPLETE", "GROSS_ONLY"}
_ALLOWED_NEWS_STATES = {"VERIFIED", "UNVERIFIED", "NO_RELEVANT_EVENT", "NOT_CHECKED"}


def _aware_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def assess_recommendation_evidence(
    evidence: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_market_age_seconds: int = 120,
) -> dict[str, Any]:
    """Return a fail-closed, auditable publication assessment.

    Required keys: symbol, timeframe, signal, candle_closed, provider_id,
    provider_verified, market_received_at, strategy_version, evidence_for,
    evidence_against, risk_invalidation, cost_status, news_status.
    """
    if not isinstance(evidence, Mapping):
        raise ValueError("evidence must be a mapping")
    if isinstance(max_market_age_seconds, bool) or not isinstance(max_market_age_seconds, int) or max_market_age_seconds < 1:
        raise ValueError("max_market_age_seconds must be a positive integer")

    required_text = ("symbol", "timeframe", "provider_id", "strategy_version")
    missing = [key for key in required_text if not isinstance(evidence.get(key), str) or not evidence[key].strip()]
    signal = evidence.get("signal")
    if signal not in _ALLOWED_SIGNALS:
        missing.append("signal")
    if evidence.get("candle_closed") is not True:
        missing.append("candle_closed")
    if evidence.get("provider_verified") is not True:
        missing.append("provider_verified")
    for key in ("evidence_for", "evidence_against"):
        value = evidence.get(key)
        if not isinstance(value, (list, tuple)) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
            missing.append(key)
    if not isinstance(evidence.get("risk_invalidation"), str) or not evidence["risk_invalidation"].strip():
        missing.append("risk_invalidation")

    cost_status = evidence.get("cost_status")
    if cost_status not in _ALLOWED_COST_STATES:
        missing.append("cost_status")
    news_status = evidence.get("news_status")
    if news_status not in _ALLOWED_NEWS_STATES:
        missing.append("news_status")

    blockers: list[str] = []
    market_age_seconds = None
    if "market_received_at" not in evidence:
        missing.append("market_received_at")
    else:
        received = _aware_timestamp(evidence.get("market_received_at"), "market_received_at")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        market_age_seconds = (current.astimezone(timezone.utc) - received).total_seconds()
        if market_age_seconds < 0:
            blockers.append("MARKET_TIMESTAMP_IN_FUTURE")
        elif market_age_seconds > max_market_age_seconds:
            blockers.append("MARKET_DATA_STALE")

    if cost_status != "NET_VERIFIED":
        blockers.append("NET_COSTS_NOT_VERIFIED")
    if news_status in {"UNVERIFIED", "NOT_CHECKED"}:
        blockers.append("NEWS_NOT_VERIFIED_OR_NOT_CHECKED")
    if missing:
        blockers.append("REQUIRED_EVIDENCE_MISSING")

    publishable = not blockers and signal in {"COMPRA", "VENDA"}
    if signal == "AGUARDAR" and not blockers:
        status = "WAIT"
    elif publishable:
        status = "EVIDENCE_READY_REQUIRES_HUMAN_REVIEW"
    else:
        status = "INSUFFICIENT_OR_UNVERIFIED"

    return {
        "status": status,
        "publishable_directional_recommendation": publishable,
        "signal": signal if publishable or signal == "AGUARDAR" else "AGUARDAR",
        "symbol": evidence.get("symbol"),
        "timeframe": evidence.get("timeframe"),
        "strategy_version": evidence.get("strategy_version"),
        "market_age_seconds": market_age_seconds,
        "evidence_for": list(evidence.get("evidence_for", [])) if isinstance(evidence.get("evidence_for"), (list, tuple)) else [],
        "evidence_against": list(evidence.get("evidence_against", [])) if isinstance(evidence.get("evidence_against"), (list, tuple)) else [],
        "risk_invalidation": evidence.get("risk_invalidation"),
        "cost_status": cost_status,
        "news_status": news_status,
        "blockers": sorted(set(blockers)),
        "probability_of_profit": None,
        "probability_status": "NOT_CALIBRATED",
        "confidence_percentage": None,
        "execution_authorized": False,
        "human_review_required": True,
    }
