from datetime import datetime, timezone

from core.risk_manager import RiskManager
from integration.p137_operational_risk_bridge import OperationalRiskBridge


def _payload():
    return {
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
        }
    }


def test_bridge_preserves_explicit_operational_state():
    state = OperationalRiskBridge.build_state(_payload())
    assert state.trades_today == 2
    assert state.consecutive_losses == 0
    assert state.balance == 2000


def test_bridge_missing_state_fails_closed():
    decision = OperationalRiskBridge(RiskManager()).evaluate({})
    assert decision.allowed is False
    assert "Estado operacional de risco inválido" in decision.reason


def test_bridge_missing_required_counters_cannot_approve():
    payload = _payload()
    payload["operational_state"].pop("trades_today")
    decision = OperationalRiskBridge(RiskManager()).evaluate(payload)
    assert decision.allowed is False
    assert "obrigatórias" in decision.reason


def test_bridge_respects_existing_risk_manager_limits():
    decision = OperationalRiskBridge(RiskManager(max_operations=2)).evaluate(_payload())
    assert decision.allowed is False
    assert "Limite de operações" in decision.reason


def test_bridge_rejects_malformed_operational_state():
    payload = _payload()
    payload["operational_state"]["consecutive_losses"] = "zero"
    decision = OperationalRiskBridge(RiskManager()).evaluate(payload)
    assert decision.allowed is False
