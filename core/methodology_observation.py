from __future__ import annotations

from dataclasses import dataclass

from data.models import Candle

from .methodology_features import CandleFeatures, extract_candle_features, same_direction


@dataclass(frozen=True)
class MethodologyObservation:
    """Transparent observations derived from the latest completed candles.

    This object describes facts only. It does not classify a trade, assign a
    strategy score, or infer thresholds for concepts not explicitly defined.
    """

    latest: CandleFeatures
    previous: CandleFeatures | None
    same_direction: bool


def observe_candles(candles: list[Candle]) -> MethodologyObservation | None:
    """Build methodology observations from completed candles, if available."""
    if not candles:
        return None
    latest = extract_candle_features(candles[-1])
    previous = extract_candle_features(candles[-2]) if len(candles) >= 2 else None
    return MethodologyObservation(
        latest=latest,
        previous=previous,
        same_direction=previous is not None and same_direction(previous, latest),
    )
