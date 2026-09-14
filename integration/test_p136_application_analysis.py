from datetime import datetime, timedelta, timezone

from core.senior_risk_reasoning import RiskDomain
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


def _candles():
    base = datetime(2026, 9, 13, tzinfo=timezone.utc)
    return [
        {"timestamp": (base + timedelta(minutes=i)).isoformat(), "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 1000 + i}
        for i in range(5)
    ]


def _risk_observations():
    return [
        {"domain": domain.value, "statement": f"{domain.value} observado.", "known": True, "evidence": ["validated-context"]}
        for domain in RiskDomain
    ]


def _payload():
    return {
        "symbol": "EURUSD",
        "timeframe": "5m",
        "score": 95,
        "confirmed": True,
        "filters_ok": True,
        "candles": _candles(),
        "available_nodes": ["market_data", "price_history", "risk", "execution", "security"],
        "observed_nodes": ["market_data", "price_history", "risk", "execution", "security"],
        "relationships_reviewed": ["price-structure", "structure-volatility", "price-liquidity", "risk-execution", "security-recovery"],
        "risk_observations": _risk_observations(),
    }


def test_application_analysis_fails_closed_for_score_only_payload():
    service = ConfiguredEcosystemService()
    record = service.analyze({"score": 99, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})
    assert record.signal == "AGUARDAR"
    assert "Análise sênior não pode ser concluída" in record.reason


def test_application_analysis_uses_complete_senior_context_before_recording():
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
