from __future__ import annotations

from dataclasses import dataclass

from .p37_market_context import MarketContextSnapshot, SymbolMarketContext
from .signal_quality import SignalQuality


@dataclass(frozen=True)
class ContextualSignalQuality:
    symbol: str
    base_quality: SignalQuality
    event_count: int
    high_impact_events: int
    medium_impact_events: int
    low_impact_events: int
    unknown_impact_events: int


class ContextualSignalQualityEvaluator:
    """Combines signal quality with declared news facts without changing direction."""

    def evaluate(
        self,
        symbol: str,
        quality: SignalQuality,
        context: MarketContextSnapshot,
    ) -> ContextualSignalQuality:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not isinstance(quality, SignalQuality):
            raise ValueError("quality is invalid")
        if not isinstance(context, MarketContextSnapshot):
            raise ValueError("context is invalid")

        normalized = symbol.strip().upper()
        matches = tuple(item for item in context.symbols if item.symbol == normalized)
        if len(matches) > 1:
            raise ValueError("context contains duplicate symbol summaries")

        item = matches[0] if matches else SymbolMarketContext(symbol=normalized, event_count=0, impact_counts=_zero_counts(), events=())
        return ContextualSignalQuality(
            symbol=normalized,
            base_quality=quality,
            event_count=item.event_count,
            high_impact_events=item.impact_counts.high,
            medium_impact_events=item.impact_counts.medium,
            low_impact_events=item.impact_counts.low,
            unknown_impact_events=item.impact_counts.unknown,
        )


def _zero_counts():
    from .p37_market_context import ImpactCounts
    return ImpactCounts()
