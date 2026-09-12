from __future__ import annotations

from dataclasses import dataclass

from .methodology_features import CandleFeatures


@dataclass(frozen=True)
class MethodologyPatternObservation:
    """Facts that can be observed without assigning a trading decision.

    The pattern names are deliberately descriptive. They do not claim that a
    detected geometry is automatically a COMPRA/VENDA setup.
    """

    latest_is_careca: bool
    two_same_direction_without_wicks: bool
    latest_wick_symmetry: float
    previous_wick_symmetry: float | None


def observe_patterns(
    latest: CandleFeatures,
    previous: CandleFeatures | None = None,
) -> MethodologyPatternObservation:
    """Expose only methodology facts already defined by candle geometry."""
    same_direction_without_wicks = bool(
        previous is not None
        and latest.has_no_wicks
        and previous.has_no_wicks
        and latest.direction != "NEUTRAL"
        and latest.direction == previous.direction
    )
    return MethodologyPatternObservation(
        latest_is_careca=latest.has_no_wicks,
        two_same_direction_without_wicks=same_direction_without_wicks,
        latest_wick_symmetry=latest.wick_symmetry,
        previous_wick_symmetry=(
            previous.wick_symmetry if previous is not None else None
        ),
    )
