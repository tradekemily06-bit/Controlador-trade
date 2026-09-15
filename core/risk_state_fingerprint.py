"""Deterministic identity for the operational risk state used by a decision.

This identity is intentionally separate from market-data identity. It is a
race-prevention primitive: a decision must not be dispatched against a risk
state different from the one that was assessed. The execution gateway will
only trust this identity once an authoritative runtime provider is wired.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json

from .operational_state import OperationalState


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def risk_state_fingerprint(state: OperationalState) -> str:
    """Return a stable SHA-256 identity for every risk-relevant field."""
    if not isinstance(state, OperationalState):
        raise ValueError("estado operacional inválido.")

    payload = {
        "balance": _json_value(state.balance),
        "equity": _json_value(state.equity),
        "realized_pnl": _json_value(state.realized_pnl),
        "unrealized_pnl": _json_value(state.unrealized_pnl),
        "trades_today": state.trades_today,
        "consecutive_losses": state.consecutive_losses,
        "open_positions": state.open_positions,
        "net_position": _json_value(state.net_position),
        "exposure": _json_value(state.exposure),
        "market_open": state.market_open,
        "last_processed_candle": _json_value(state.last_processed_candle),
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
