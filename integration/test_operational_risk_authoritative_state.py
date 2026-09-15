from datetime import datetime, timezone

from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.operational_state import OperationalState
from core.risk_manager import RiskManager
from integration.p137_operational_risk_bridge import OperationalRiskBridge


def _ready_barrier():
    return GlobalOperationalBarrier(
        components=(SafetyComponent(name="test-runtime", healthy=True, detail="ready"),)
    )


def _authoritative_state(*, trades_today: int = 0):
    return OperationalState(
        balance=2000,
        equity=2000,
        realized_pnl=0,
        trades_today=trades_today,
        consecutive_losses=0,
        open_positions=0,
        exposure=0,
        market_open=True,
        last_processed_candle=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )


def _payload_with_spoofed_state():
    return {
        "operational_state": {
            "balance": 2000,
            "equity": 2000,
            "realized_pnl": 0,
            "trades_today": 999,
            "consecutive_losses": 999,
            "open_positions": 999,
            "exposure": 999999,
            "market_open": True,
            "last_processed_candle": datetime(2026, 9, 15, tzinfo=timezone.utc).isoformat(),
        }
    }


def test_bound_bridge_ignores_payload_risk_state_and_uses_authoritative_runtime():
    bridge = OperationalRiskBridge(
        RiskManager(max_operations=1, max_consecutive_losses=1),
        operational_barrier_provider=_ready_barrier,
        operational_state_provider=lambda: _authoritative_state(trades_today=0),
    )

    decision = bridge.evaluate(_payload_with_spoofed_state())

    assert decision.allowed is True


def test_bound_bridge_blocks_when_authoritative_runtime_state_is_unavailable():
    bridge = OperationalRiskBridge(
        RiskManager(),
        operational_barrier_provider=_ready_barrier,
        operational_state_provider=lambda: None,
    )

    decision = bridge.evaluate(_payload_with_spoofed_state())

    assert decision.allowed is False
    assert "fonte autoritativa" in decision.reason
