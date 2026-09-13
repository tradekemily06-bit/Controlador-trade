from __future__ import annotations

from dataclasses import dataclass

from .general_market_observation import GeneralMarketObservation
from .market_discovery import discover_market_relationships


@dataclass(frozen=True)
class MarketContextReasoning:
    """Neutral combinations of observations, without a trade decision."""

    directional_balance: str
    structure_context: str
    participation_context: str
    expansion_context: str
    pattern_context: tuple[str, ...]
    discovered_relationships: tuple[str, ...]


def reason_market_context(
    observation: GeneralMarketObservation | None,
) -> MarketContextReasoning | None:
    """Combine broad observations into explainable context only.

    This layer intentionally does not emit COMPRA, VENDA, score, entry,
    confidence, or risk decisions. It also does not invent numeric thresholds.
    Open-ended relationship discovery is exposed as neutral evidence only.
    """
    if observation is None:
        return None

    if observation.bullish_count > observation.bearish_count:
        directional_balance = "BULLISH_CONTEXT"
    elif observation.bearish_count > observation.bullish_count:
        directional_balance = "BEARISH_CONTEXT"
    elif observation.neutral_count == observation.candle_count:
        directional_balance = "NEUTRAL_CONTEXT"
    else:
        directional_balance = "MIXED_CONTEXT"

    if (
        observation.high_progression == "HIGHER"
        and observation.low_progression == "HIGHER"
    ):
        structure_context = "RISING_BOUNDS"
    elif (
        observation.high_progression == "LOWER"
        and observation.low_progression == "LOWER"
    ):
        structure_context = "FALLING_BOUNDS"
    elif (
        observation.high_progression != "UNDEFINED"
        and observation.low_progression != "UNDEFINED"
    ):
        structure_context = "MIXED_BOUNDS"
    else:
        structure_context = "UNDEFINED"

    if observation.volume_change == "UP":
        participation_context = "VOLUME_EXPANDING"
    elif observation.volume_change == "DOWN":
        participation_context = "VOLUME_CONTRACTING"
    else:
        participation_context = "VOLUME_UNDEFINED_OR_EQUAL"

    if observation.range_change == "UP":
        expansion_context = "RANGE_EXPANDING"
    elif observation.range_change == "DOWN":
        expansion_context = "RANGE_CONTRACTING"
    else:
        expansion_context = "RANGE_UNDEFINED_OR_EQUAL"

    patterns: list[str] = []
    if observation.same_direction_streak >= 2:
        patterns.append("DIRECTION_STREAK_PRESENT")
    if observation.range_change == "UP" and observation.volume_change == "UP":
        patterns.append("RANGE_AND_VOLUME_EXPANSION")
    if observation.range_change == "DOWN" and observation.volume_change == "DOWN":
        patterns.append("RANGE_AND_VOLUME_CONTRACTION")
    if observation.close_progression == "HIGHER":
        patterns.append("LATEST_CLOSE_HIGHER_THAN_PREVIOUS")
    elif observation.close_progression == "LOWER":
        patterns.append("LATEST_CLOSE_LOWER_THAN_PREVIOUS")
    if "LATEST_HAS_NO_WICKS:true" in observation.observations:
        patterns.append("LATEST_NO_WICK_OBSERVATION")

    return MarketContextReasoning(
        directional_balance=directional_balance,
        structure_context=structure_context,
        participation_context=participation_context,
        expansion_context=expansion_context,
        pattern_context=tuple(patterns),
        discovered_relationships=discover_market_relationships(observation),
    )
