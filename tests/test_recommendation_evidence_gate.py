from datetime import datetime, timezone

import pytest

from analysis.recommendation_evidence_gate import assess_recommendation_evidence


NOW = datetime(2026, 11, 28, 20, 0, tzinfo=timezone.utc)


def valid_evidence():
    return {
        "symbol": "EURUSD",
        "timeframe": "5m",
        "signal": "COMPRA",
        "candle_closed": True,
        "provider_id": "provider-demo",
        "provider_verified": True,
        "market_received_at": "2026-11-28T19:59:30+00:00",
        "strategy_version": "technical-pipeline-v1",
        "evidence_for": ["Tendência alinhada", "Momentum positivo"],
        "evidence_against": ["Resistência próxima"],
        "risk_invalidation": "Fechamento abaixo do último fundo",
        "cost_status": "NET_VERIFIED",
        "news_status": "NO_RELEVANT_EVENT",
    }


def test_ready_signal_never_claims_calibrated_probability():
    result = assess_recommendation_evidence(valid_evidence(), now=NOW)
    assert result["status"] == "EVIDENCE_READY_REQUIRES_HUMAN_REVIEW"
    assert result["publishable_directional_recommendation"] is True
    assert result["probability_of_profit"] is None
    assert result["confidence_percentage"] is None
    assert result["execution_authorized"] is False


@pytest.mark.parametrize("cost_status", ["INCOMPLETE", "GROSS_ONLY"])
def test_unknown_or_gross_costs_block_directional_recommendation(cost_status):
    evidence = valid_evidence()
    evidence["cost_status"] = cost_status
    result = assess_recommendation_evidence(evidence, now=NOW)
    assert result["publishable_directional_recommendation"] is False
    assert "NET_COSTS_NOT_VERIFIED" in result["blockers"]
    assert result["signal"] == "AGUARDAR"


def test_stale_market_data_blocks_recommendation():
    evidence = valid_evidence()
    evidence["market_received_at"] = "2026-11-28T19:55:00+00:00"
    result = assess_recommendation_evidence(evidence, now=NOW, max_market_age_seconds=120)
    assert result["publishable_directional_recommendation"] is False
    assert "MARKET_DATA_STALE" in result["blockers"]


def test_unverified_news_and_missing_counter_evidence_block():
    evidence = valid_evidence()
    evidence["news_status"] = "UNVERIFIED"
    evidence["evidence_against"] = []
    result = assess_recommendation_evidence(evidence, now=NOW)
    assert result["publishable_directional_recommendation"] is False
    assert "NEWS_NOT_VERIFIED_OR_NOT_CHECKED" in result["blockers"]
    assert "REQUIRED_EVIDENCE_MISSING" in result["blockers"]


def test_wait_signal_stays_wait_even_when_evidence_is_complete():
    evidence = valid_evidence()
    evidence["signal"] = "AGUARDAR"
    result = assess_recommendation_evidence(evidence, now=NOW)
    assert result["status"] == "WAIT"
    assert result["signal"] == "AGUARDAR"
