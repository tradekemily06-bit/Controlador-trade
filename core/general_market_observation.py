from __future__ import annotations

from dataclasses import dataclass

from data.models import Candle

from .methodology_features import CandleFeatures, extract_candle_features


@dataclass(frozen=True)
class GeneralMarketObservation:
    """Broad, broker-independent observations over a completed candle sequence.

    This is intentionally not a closed list of trading concepts. It records
    measurable relationships so later reasoning can discover and name patterns
    without forcing every observation into a predefined methodology rule.
    """

    candle_count: int
    directions: tuple[str, ...]
    bullish_count: int
    bearish_count: int
    neutral_count: int
    same_direction_streak: int
    latest_range: float
    previous_range: float | None
    range_change: str
    latest_body: float
    previous_body: float | None
    body_change: str
    latest_volume: float
    previous_volume: float | None
    volume_change: str
    high_progression: str
    low_progression: str
    close_progression: str
    observations: tuple[str, ...]


def _change(current: float, previous: float | None) -> str:
    if previous is None:
        return "UNDEFINED"
    if current > previous:
        return "UP"
    if current < previous:
        return "DOWN"
    return "EQUAL"


def _progression(current: float, previous: float | None) -> str:
    if previous is None:
        return "UNDEFINED"
    if current > previous:
        return "HIGHER"
    if current < previous:
        return "LOWER"
    return "EQUAL"


def _same_direction_streak(features: list[CandleFeatures]) -> int:
    if not features or features[-1].direction == "NEUTRAL":
        return 0
    direction = features[-1].direction
    streak = 0
    for feature in reversed(features):
        if feature.direction != direction:
            break
        streak += 1
    return streak


def observe_general_market_context(
    candles: list[Candle],
) -> GeneralMarketObservation | None:
    """Observe broad candle/sequence context without producing a trade signal."""
    if not candles:
        return None
    if not all(candle.is_valid() for candle in candles):
        raise ValueError("all candles must be valid")

    features = [extract_candle_features(candle) for candle in candles]
    latest = features[-1]
    previous = features[-2] if len(features) >= 2 else None
    latest_candle = candles[-1]
    previous_candle = candles[-2] if len(candles) >= 2 else None

    directions = tuple(feature.direction for feature in features)
    bullish_count = sum(direction == "ALTA" for direction in directions)
    bearish_count = sum(direction == "BAIXA" for direction in directions)
    neutral_count = sum(direction == "NEUTRAL" for direction in directions)
    streak = _same_direction_streak(features)

    range_change = _change(latest.range_size, previous.range_size if previous else None)
    body_change = _change(latest.body_size, previous.body_size if previous else None)
    volume_change = _change(
        latest_candle.volume,
        previous_candle.volume if previous_candle else None,
    )
    high_progression = _progression(
        latest_candle.high,
        previous_candle.high if previous_candle else None,
    )
    low_progression = _progression(
        latest_candle.low,
        previous_candle.low if previous_candle else None,
    )
    close_progression = _progression(
        latest_candle.close,
        previous_candle.close if previous_candle else None,
    )

    observations = [
        f"LATEST_DIRECTION:{latest.direction}",
        f"LATEST_WICK:{latest.dominant_wick}",
        f"LATEST_CLOSE_POSITION:{latest.close_position:.6f}",
        f"LATEST_BODY_RATIO:{latest.body_ratio:.6f}",
        f"LATEST_WICK_SYMMETRY:{latest.wick_symmetry:.6f}",
        f"LATEST_HAS_NO_WICKS:{str(latest.has_no_wicks).lower()}",
        f"DIRECTION_STREAK:{streak}",
        f"RANGE_CHANGE:{range_change}",
        f"BODY_CHANGE:{body_change}",
        f"VOLUME_CHANGE:{volume_change}",
        f"HIGH_PROGRESS:{high_progression}",
        f"LOW_PROGRESS:{low_progression}",
        f"CLOSE_PROGRESS:{close_progression}",
    ]

    return GeneralMarketObservation(
        candle_count=len(candles),
        directions=directions,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        neutral_count=neutral_count,
        same_direction_streak=streak,
        latest_range=latest.range_size,
        previous_range=previous.range_size if previous else None,
        range_change=range_change,
        latest_body=latest.body_size,
        previous_body=previous.body_size if previous else None,
        body_change=body_change,
        latest_volume=latest_candle.volume,
        previous_volume=previous_candle.volume if previous_candle else None,
        volume_change=volume_change,
        high_progression=high_progression,
        low_progression=low_progression,
        close_progression=close_progression,
        observations=tuple(observations),
    )
