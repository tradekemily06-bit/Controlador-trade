"""Translate explicit application/runtime risk state into the operational risk gate.

The bridge does not invent missing values and does not duplicate RiskManager
policy. It only validates the boundary, builds OperationalState, and delegates
risk evaluation to the existing RiskManager.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from core.operational_state import OperationalState, OperationalStateValidationError
from core.risk_manager import RiskDecision, RiskManager


class OperationalRiskBridge:
    """Fail-closed adapter between application payloads and RiskManager."""

    def __init__(self, risk_manager: RiskManager) -> None:
        if not isinstance(risk_manager, RiskManager):
            raise ValueError("risk_manager must be RiskManager")
        self.risk_manager = risk_manager

    def evaluate(self, payload: Mapping[str, Any]) -> RiskDecision:
        try:
            state = self.build_state(payload)
        except (TypeError, ValueError, OperationalStateValidationError):
            return RiskDecision(False, "Estado operacional de risco inválido.")
        return self.risk_manager.evaluate(state=state)

    @staticmethod
    def build_state(payload: Mapping[str, Any]) -> OperationalState:
        if not isinstance(payload, Mapping):
            raise ValueError("analysis payload must be an object")
        raw = payload.get("operational_state")
        if not isinstance(raw, Mapping):
            raise ValueError("operational_state is required for risk approval")

        fields = {
            "balance": raw.get("balance"),
            "equity": raw.get("equity"),
            "realized_pnl": raw.get("realized_pnl"),
            "unrealized_pnl": raw.get("unrealized_pnl"),
            "trades_today": raw.get("trades_today"),
            "consecutive_losses": raw.get("consecutive_losses"),
            "open_positions": raw.get("open_positions"),
            "net_position": raw.get("net_position"),
            "exposure": raw.get("exposure"),
            "market_open": raw.get("market_open"),
        }
        timestamp = raw.get("last_processed_candle")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        fields["last_processed_candle"] = timestamp
        return OperationalState(**fields)
