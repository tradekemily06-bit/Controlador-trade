from datetime import datetime, timezone

import pytest

from core.senior_risk_reasoning import RiskDomain
from integration.p135_senior_analysis_boundary import SeniorAnalysisBoundary


def _payload():
    return {
        "symbol": "EURUSD",
        "candles": [
            {"timestamp": "2026-09-13T12:00:00+00:00", "open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1008, "volume": 100},
            {"timestamp": "2026-09-13T12:05:00+00:00", "open": 1.1008, "high": 1.1020, "low": 1.1002, "close": 1.1016, "volume": 120},
        ],
        "observed_nodes": ["market_data", "price_history", "risk", "execution", "security"],
        "relationships_reviewed": ["price_history->market_data", "market_data->risk"],
        "risk_observations": [
            {"domain": "DATA_QUALITY", "statement": "Dados completos e consistentes.", "known": True, "evidence": ["feed-check"]}
        ],
    }


def test_builds_valid_senior_context_input():
    result = SeniorAnalysisBoundary.build_input(_payload())
    assert result.context_id.startswith("analysis:EURUSD:")
    assert len(result.candles) == 2
    assert result.candles[-1].timestamp == datetime(2026, 9, 13, 12, 5, tzinfo=timezone.utc)
    assert result.risk_observations[0].domain is RiskDomain.DATA_QUALITY


def test_requires_market_candles():
    payload = _payload()
    payload.pop("candles")
    with pytest.raises(ValueError, match="candles are required"):
        SeniorAnalysisBoundary.build_input(payload)


def test_rejects_invalid_candle():
    payload = _payload()
    payload["candles"][0]["high"] = 1.098
    with pytest.raises(ValueError, match="invalid candle"):
        SeniorAnalysisBoundary.build_input(payload)


def test_rejects_unknown_risk_domain():
    payload = _payload()
    payload["risk_observations"][0]["domain"] = "UNKNOWN_DOMAIN"
    with pytest.raises(ValueError, match="invalid risk observation domain"):
        SeniorAnalysisBoundary.build_input(payload)