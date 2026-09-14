from datetime import datetime, timedelta, timezone

import pytest

from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


def _candles():
    base = datetime(2026, 9, 13, tzinfo=timezone.utc)
    return [
        {"timestamp": (base + timedelta(minutes=i)).isoformat(), "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 1000 + i}
        for i in range(5)
    ]


def _payload():
    return {
        "symbol": "EURUSD",
        "timeframe": "5m",
        "score": 95,
        "confirmed": True,
        "filters_ok": True,
        "candles": _candles(),
        "available_nodes": ["price", "structure", "volatility", "liquidity"],
        "observed_nodes": ["price", "structure", "volatility", "liquidity"],
        "relationships_reviewed": ["price-structure", "structure-volatility", "price-liquidity"],
        "risk_observations": [{"domain": "CAPITAL", "statement": "Capital observado.", "known": True, "evidence": ["account"]}],
    }


def test_application_analysis_rejects_score_only_payload():
    service = ConfiguredEcosystemService()
    with pytest.raises(ValueError, match="candles are required"):
        service.analyze({"score": 99, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})


def test_application_analysis_uses_senior_context_before_recording():
    service = ConfiguredEcosystemService()
    record = service.analyze(_payload())
    assert record.signal == "COMPRA"
    assert record.score == 95


def test_application_analysis_does_not_store_unsupported_direction():
    service = ConfiguredEcosystemService()
    payload = _payload()
    payload["score"] = 5
    payload["confirmed"] = True
    record = service.analyze(payload)
    assert record.signal == "AGUARDAR"
