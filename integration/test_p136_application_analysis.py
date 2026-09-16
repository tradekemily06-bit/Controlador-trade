from datetime import datetime, timedelta, timezone

from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.senior_risk_reasoning import RiskDomain
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from integration.p137_operational_risk_bridge import OperationalRiskBridge


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
        "operational_state": {
            "balance": 2000,
            "equity": 2000,
            "realized_pnl": 0,
            "trades_today": 2,
            "consecutive_losses": 0,
            "open_positions": 0,
            "exposure": 0,
            "market_open": True,
            "last_processed_candle": datetime(2026, 9, 13, tzinfo=timezone.utc).isoformat(),
        },
    }


def _ready_barrier():
    return GlobalOperationalBarrier(
        components=(SafetyComponent(name="test-runtime", healthy=True, detail="ready"),)
    )


def _service_with_ready_risk():
    service = ConfiguredEcosystemService()
    service.operational_risk_bridge = OperationalRiskBridge(
        service.risk,
        operational_barrier_provider=_ready_barrier,
    )
    return service


def test_application_analysis_fails_closed_for_score_only_payload():
    service = ConfiguredEcosystemService()
    record = service.analyze({"score": 99, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})
    assert record.signal == "AGUARDAR"
    assert "Análise sênior não pode ser concluída" in record.reason


def test_application_analysis_uses_complete_senior_context_and_operational_risk():
    service = _service_with_ready_risk()
    record = service.analyze(_payload())
    assert record.signal == "COMPRA"
    assert record.score == 95


def test_application_analysis_blocks_when_operational_risk_state_is_missing():
    service = _service_with_ready_risk()
    payload = _payload()
    payload.pop("operational_state")
    record = service.analyze(payload)
    assert record.signal == "AGUARDAR"
    assert "Estado operacional de risco inválido" in record.reason


def test_application_analysis_blocks_when_operational_risk_limit_denies():
    service = _service_with_ready_risk()
    service.risk = service.risk.__class__(max_operations=2)
    service.operational_risk_bridge = OperationalRiskBridge(
        service.risk,
        operational_barrier_provider=_ready_barrier,
    )
    record = service.analyze(_payload())
    assert record.signal == "AGUARDAR"
    assert "Limite de operações" in record.reason


def test_application_analysis_does_not_store_unsupported_direction():
    service = _service_with_ready_risk()
    payload = _payload()
    payload["score"] = 5
    payload["confirmed"] = True
    record = service.analyze(payload)
    assert record.signal == "AGUARDAR"
