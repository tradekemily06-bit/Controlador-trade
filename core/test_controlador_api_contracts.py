import pytest

from core.controlador_api_contracts import (
    APIEnvironment,
    APIStatus,
    AnalysisRequest,
    AuditEvent,
    HealthResponse,
    MarketDataRequest,
    SignalResponse,
)
from core.models import Signal


def test_market_data_request_validates_required_fields():
    request = MarketDataRequest(symbol="BTCUSD", timeframe="5m", limit=25)

    assert request.symbol == "BTCUSD"
    assert request.limit == 25

    with pytest.raises(ValueError):
        MarketDataRequest(symbol="", timeframe="5m")
    with pytest.raises(ValueError):
        MarketDataRequest(symbol="BTCUSD", timeframe="5m", limit=0)


def test_analysis_request_defaults_to_demo():
    request = AnalysisRequest(symbol="BTCUSD")

    assert request.environment is APIEnvironment.DEMO
    assert request.timeframe == "5m"
    assert request.candle_limit == 50


def test_analysis_request_rejects_real_as_invalid_environment_value():
    with pytest.raises(ValueError):
        AnalysisRequest(symbol="BTCUSD", environment="REAL")


def test_blocked_signal_response_is_always_aguardar_and_real():
    response = SignalResponse.blocked(reason="REAL execution is disabled")

    assert response.status is APIStatus.BLOCKED
    assert response.signal is Signal.AGUARDAR
    assert response.confirmed is False
    assert response.environment is APIEnvironment.REAL


def test_health_and_audit_contracts_are_broker_agnostic():
    health = HealthResponse(
        status=APIStatus.OK,
        environment=APIEnvironment.DEMO,
        broker_connected=True,
        message="connected",
    )
    audit = AuditEvent(
        event="analysis.completed",
        status=APIStatus.OK,
        environment=APIEnvironment.DEMO,
        symbol="BTCUSD",
        detail="read-only analysis",
    )

    assert health.broker_connected is True
    assert audit.symbol == "BTCUSD"
    assert audit.environment is APIEnvironment.DEMO
