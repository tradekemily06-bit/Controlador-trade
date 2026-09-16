from datetime import datetime, timezone

from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.risk_manager import RiskManager
from integration.p137_operational_risk_bridge import OperationalRiskBridge


def _payload(*, exposure=2000):
    return {
        "operational_state": {
            "balance": 1000,
            "equity": 1000,
            "realized_pnl": 0,
            "trades_today": 0,
            "consecutive_losses": 0,
            "open_positions": 0,
            "net_position": 0,
            "exposure": exposure,
            "market_open": True,
            "last_processed_candle": datetime(2026, 9, 15, tzinfo=timezone.utc).isoformat(),
        },
        "leverage_request": {
            "request_id": "risk-1",
            "profile_id": "demo",
            "symbol": "EURUSD",
            "requested_leverage": 2,
            "capital_allocated": 1000,
            "quantity": 1,
            "price": 1.1,
            "stop_distance": 10,
            "value_per_price_unit": 1,
            "maximum_loss": 10,
            "environment": "DEMO",
            "margin_required": 500,
        },
    }


def _ready_barrier():
    return GlobalOperationalBarrier(
        components=(SafetyComponent(name="test-runtime", healthy=True, detail="ready"),)
    )


def _bridge():
    return OperationalRiskBridge(
        RiskManager(),
        operational_barrier_provider=_ready_barrier,
    )


def test_leverage_and_operational_exposure_must_reconcile():
    decision = _bridge().evaluate(_payload())
    assert decision.allowed is True


def test_conflicting_exposure_fails_closed():
    decision = _bridge().evaluate(_payload(exposure=1999))
    assert decision.allowed is False
    assert "diverge" in decision.reason


def test_missing_exposure_fails_closed_when_leverage_is_present():
    payload = _payload()
    payload["operational_state"]["exposure"] = None
    decision = _bridge().evaluate(payload)
    assert decision.allowed is False
    assert "Exposição operacional ausente" in decision.reason


def test_leverage_loss_budget_blocks_even_when_operational_limits_are_clear():
    payload = _payload()
    payload["leverage_request"]["maximum_loss"] = 9
    decision = _bridge().evaluate(payload)
    assert decision.allowed is False
    assert "orçamento" in decision.reason


def test_partial_leverage_payload_never_gets_silent_approval():
    payload = _payload()
    payload["leverage_request"].pop("margin_required")
    decision = _bridge().evaluate(payload)
    assert decision.allowed is False
    assert "reavaliação" in decision.reason
