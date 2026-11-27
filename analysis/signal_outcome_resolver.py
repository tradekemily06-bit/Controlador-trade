"""Conservative, timeframe-exact directional outcome labels for signal audits.

This module does not calculate net profit, execution probability, or calibrated
win probability. It labels the next exact-timeframe real-market candle only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from data.timeframes import get_timeframe_interval, normalize_timeframe


@dataclass(frozen=True)
class DirectionalOutcome:
    signal_id: str
    symbol: str
    timeframe: str
    direction: str
    outcome: bool | None
    outcome_status: str
    outcome_definition: str
    candle_open_at: str | None
    candle_close_at: str | None
    provenance: str
    net_profit_status: str = "NOT_ASSESSED"
    probability_of_profit: None = None


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field} must be finite") from exc
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite")
    return result


def resolve_next_candle_direction(
    signal: Mapping[str, Any],
    candle: Mapping[str, Any],
    *,
    provenance: str,
) -> DirectionalOutcome:
    """Resolve only the next exact-timeframe candle after a recorded signal.

    The candle's open timestamp must equal the signal candle's close timestamp.
    This avoids silently using a later bar or borrowing another timeframe.
    A doji is UNRESOLVED, not a win or loss. This is directional accuracy only;
    spread, commissions, slippage, entry latency and position sizing are absent.
    """
    if provenance != "REAL_MARKET_DATA":
        raise ValueError("only real market data can resolve this audit label")

    required_signal = (
        "signal_id", "symbol", "timeframe", "direction",
        "candle_close_at", "observed_at", "valid_until",
    )
    if any(not isinstance(signal.get(key), str) or not signal[key].strip()
           for key in required_signal):
        raise ValueError("signal audit context is incomplete")

    symbol = signal["symbol"].strip().upper()
    candle_symbol = candle.get("symbol")
    if not isinstance(candle_symbol, str) or candle_symbol.strip().upper() != symbol:
        raise ValueError("candle symbol does not match signal symbol")

    timeframe = normalize_timeframe(signal["timeframe"])
    candle_timeframe = normalize_timeframe(candle.get("timeframe"))
    if candle_timeframe != timeframe:
        raise ValueError("candle timeframe does not match signal timeframe")

    direction = signal["direction"].strip().upper()
    if direction not in {"COMPRA", "VENDA"}:
        raise ValueError("only actionable COMPRA or VENDA signals can be resolved")

    boundary = _timestamp(signal["candle_close_at"], "candle_close_at")
    observed = _timestamp(signal["observed_at"], "observed_at")
    valid_until = _timestamp(signal["valid_until"], "valid_until")
    candle_open_at = _timestamp(candle.get("open_time"), "open_time")
    candle_close_at = candle_open_at + get_timeframe_interval(timeframe)

    # Never score a bar that had already closed before the signal existed.
    # Otherwise historical evaluation would leak future information.
    if candle_close_at <= observed:
        raise ValueError("outcome candle closed before signal was observed")

    if observed < boundary:
        raise ValueError("signal observation cannot precede its closed candle")
    if observed >= valid_until:
        raise ValueError("signal was already expired when observed")
    if candle_open_at != boundary:
        raise ValueError("outcome candle is not the immediate next candle")
    if candle_close_at > valid_until:
        raise ValueError("outcome candle closes after signal validity expires")

    opened = _number(candle.get("open"), "open")
    closed = _number(candle.get("close"), "close")
    high = _number(candle.get("high"), "high")
    low = _number(candle.get("low"), "low")
    if low > min(opened, closed) or high < max(opened, closed) or low > high:
        raise ValueError("candle OHLC values are inconsistent")

    if closed == opened:
        outcome = None
        status = "UNRESOLVED_DOJI"
    else:
        outcome = closed > opened if direction == "COMPRA" else closed < opened
        status = "DIRECTIONAL_HIT" if outcome else "DIRECTIONAL_MISS"

    return DirectionalOutcome(
        signal_id=signal["signal_id"].strip(),
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        outcome=outcome,
        outcome_status=status,
        outcome_definition="NEXT_CANDLE_CLOSE_VS_OPEN_DIRECTION_ONLY",
        candle_open_at=candle_open_at.isoformat(),
        candle_close_at=candle_close_at.isoformat(),
        provenance=provenance,
    )


def resolve_next_candle_direction_safe(
    signal: Mapping[str, Any],
    candle: Mapping[str, Any],
    *,
    provenance: str,
) -> dict[str, Any]:
    """Serialize an outcome label without implying financial profitability."""
    result = resolve_next_candle_direction(signal, candle, provenance=provenance)
    return {
        "signal_id": result.signal_id,
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "direction": result.direction,
        "outcome": result.outcome,
        "outcome_status": result.outcome_status,
        "outcome_definition": result.outcome_definition,
        "candle_open_at": result.candle_open_at,
        "candle_close_at": result.candle_close_at,
        "provenance": result.provenance,
        "net_profit_status": result.net_profit_status,
        "probability_of_profit": result.probability_of_profit,
        "calibration_eligible": False,
        "reason": (
            "Rótulo direcional sem spread, comissão, slippage ou execução; "
            "não é resultado financeiro nem probabilidade de lucro."
        ),
    }
