"""Mandatory senior-context boundary for application analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from core.p55_trusted_knowledge import TrustedKnowledge
from core.senior_context_orchestrator import SeniorContextInput
from core.senior_risk_reasoning import RiskDomain, RiskObservation
from data.models import Candle


class SeniorAnalysisBoundary:
    """Build the explicit senior-context input required by application analysis."""

    @staticmethod
    def build_input(payload: Mapping[str, Any]) -> SeniorContextInput:
        if not isinstance(payload, Mapping):
            raise ValueError("analysis payload must be an object")
        candles_payload = payload.get("candles")
        if not isinstance(candles_payload, (list, tuple)) or not candles_payload:
            raise ValueError("candles are required for senior analysis")
        candles = tuple(SeniorAnalysisBoundary._candle(item) for item in candles_payload)
        risk_observations = tuple(SeniorAnalysisBoundary._risk_observation(item) for item in (payload.get("risk_observations") or ()))
        available_nodes = SeniorAnalysisBoundary._strings(payload.get("available_nodes"), default=("market_data", "price_history", "risk", "execution", "security"))
        observed_nodes = SeniorAnalysisBoundary._strings(payload.get("observed_nodes"))
        relationships_reviewed = SeniorAnalysisBoundary._strings(payload.get("relationships_reviewed"))
        validated_knowledge_ids = SeniorAnalysisBoundary._strings(payload.get("validated_knowledge_ids"))
        trusted_knowledge = tuple(SeniorAnalysisBoundary._trusted_knowledge(item) for item in (payload.get("trusted_knowledge") or ()))
        if validated_knowledge_ids and not trusted_knowledge:
            raise ValueError("trusted_knowledge is required when validated_knowledge_ids are supplied")
        gaps = payload.get("gaps") or {}
        if not isinstance(gaps, Mapping):
            raise ValueError("gaps must be an object")
        return SeniorContextInput(
            context_id=str(payload.get("context_id") or f"analysis:{payload.get('symbol') or 'unknown'}:{candles[-1].timestamp.isoformat()}"),
            candles=candles,
            available_nodes=available_nodes,
            observed_nodes=observed_nodes,
            gaps={str(key): str(value) for key, value in gaps.items()},
            relationships_reviewed=relationships_reviewed,
            risk_observations=risk_observations,
            validated_knowledge_ids=validated_knowledge_ids,
            available_risk_domains=tuple(RiskDomain),
            trusted_knowledge=trusted_knowledge,
        )

    @staticmethod
    def _candle(value: Any) -> Candle:
        if not isinstance(value, Mapping):
            raise ValueError("each candle must be an object")
        timestamp = value.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if not isinstance(timestamp, datetime):
            raise ValueError("candle timestamp must be an ISO datetime")
        try:
            candle = Candle(timestamp=timestamp, open=float(value["open"]), high=float(value["high"]), low=float(value["low"]), close=float(value["close"]), volume=float(value.get("volume", 0.0)))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid candle") from exc
        if not candle.is_valid():
            raise ValueError("invalid candle")
        return candle

    @staticmethod
    def _risk_observation(value: Any) -> RiskObservation:
        if not isinstance(value, Mapping):
            raise ValueError("each risk observation must be an object")
        try:
            domain = RiskDomain(str(value["domain"]).upper())
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid risk observation domain") from exc
        statement = str(value.get("statement", "")).strip()
        if not statement:
            raise ValueError("risk observation statement is required")
        known = value.get("known")
        if not isinstance(known, bool):
            raise ValueError("risk observation known must be boolean")
        evidence = value.get("evidence") or ()
        if not isinstance(evidence, (list, tuple)):
            raise ValueError("risk observation evidence must be a list")
        return RiskObservation(domain=domain, statement=statement, known=known, evidence=tuple(str(item) for item in evidence))

    @staticmethod
    def _trusted_knowledge(value: Any) -> TrustedKnowledge:
        if not isinstance(value, Mapping):
            raise ValueError("each trusted knowledge item must be an object")
        required = ("knowledge_id", "hypothesis_id", "test_id", "statement", "source_observation")
        if any(key not in value for key in required):
            raise ValueError("trusted knowledge is incomplete")
        fields = {key: str(value[key]).strip() for key in required}
        if any(not item for item in fields.values()):
            raise ValueError("trusted knowledge fields must be non-empty")
        return TrustedKnowledge(**fields)

    @staticmethod
    def _strings(value: Any, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
        if value is None:
            return default
        if not isinstance(value, (list, tuple)):
            raise ValueError("context node fields must be lists")
        return tuple(str(item).strip() for item in value if str(item).strip())
