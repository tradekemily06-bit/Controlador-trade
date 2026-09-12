from __future__ import annotations

from dataclasses import dataclass

from data.models import Candle


@dataclass(frozen=True)
class CandleFeatures:
    """Raw, broker-independent candle geometry for the trading methodology layer.

    This layer measures observable candle facts only. It deliberately does not
    decide COMPRA/VENDA, assign a score, or invent thresholds for the user's
    methodology.
    """

    direction: str
    range_size: float
    body_size: float
    upper_wick: float
    lower_wick: float
    body_ratio: float
    upper_wick_ratio: float
    lower_wick_ratio: float
    close_position: float
    has_no_upper_wick: bool
    has_no_lower_wick: bool
    has_no_wicks: bool
    wick_symmetry: float
    dominant_wick: str
    wick_to_body_ratio: float | None


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _dominant_wick(upper_wick: float, lower_wick: float) -> str:
    if upper_wick == 0 and lower_wick == 0:
        return "NONE"
    if upper_wick == lower_wick:
        return "BOTH_EQUAL"
    return "UPPER" if upper_wick > lower_wick else "LOWER"


def extract_candle_features(candle: Candle) -> CandleFeatures:
    """Extract deterministic geometry from one validated candle.

    Ratios are normalized to the candle's total range. A zero/invalid range
    fails closed with neutral zeroed measurements rather than inventing data.
    """
    if not candle.is_valid():
        raise ValueError("candle must be valid")

    candle_range = candle.high - candle.low
    if candle_range <= 0:
        return CandleFeatures(
            direction="NEUTRAL",
            range_size=0.0,
            body_size=0.0,
            upper_wick=0.0,
            lower_wick=0.0,
            body_ratio=0.0,
            upper_wick_ratio=0.0,
            lower_wick_ratio=0.0,
            close_position=0.0,
            has_no_upper_wick=True,
            has_no_lower_wick=True,
            has_no_wicks=True,
            wick_symmetry=1.0,
            dominant_wick="NONE",
            wick_to_body_ratio=None,
        )

    body_size = abs(candle.close - candle.open)
    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low
    close_position = _clamp_unit((candle.close - candle.low) / candle_range)
    upper_ratio = upper_wick / candle_range
    lower_ratio = lower_wick / candle_range
    body_ratio = body_size / candle_range

    if candle.close > candle.open:
        direction = "ALTA"
    elif candle.close < candle.open:
        direction = "BAIXA"
    else:
        direction = "NEUTRAL"

    smaller_wick = min(upper_wick, lower_wick)
    larger_wick = max(upper_wick, lower_wick)
    wick_symmetry = 1.0 if larger_wick == 0 else smaller_wick / larger_wick
    total_wick = upper_wick + lower_wick
    wick_to_body_ratio = total_wick / body_size if body_size > 0 else None

    return CandleFeatures(
        direction=direction,
        range_size=candle_range,
        body_size=body_size,
        upper_wick=upper_wick,
        lower_wick=lower_wick,
        body_ratio=body_ratio,
        upper_wick_ratio=upper_ratio,
        lower_wick_ratio=lower_ratio,
        close_position=close_position,
        has_no_upper_wick=upper_wick == 0,
        has_no_lower_wick=lower_wick == 0,
        has_no_wicks=upper_wick == 0 and lower_wick == 0,
        wick_symmetry=wick_symmetry,
        dominant_wick=_dominant_wick(upper_wick, lower_wick),
        wick_to_body_ratio=wick_to_body_ratio,
    )


def same_direction(first: CandleFeatures, second: CandleFeatures) -> bool:
    """Return whether two non-neutral candles have the same direction."""
    return (
        first.direction != "NEUTRAL"
        and second.direction != "NEUTRAL"
        and first.direction == second.direction
    )
