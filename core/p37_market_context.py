from __future__ import annotations

from dataclasses import dataclass

from core.p36_market_context import MarketContext, NewsEvent, NewsImpact


@dataclass(frozen=True)
class ImpactCounts:
    low: int = 0
    medium: int = 0
    high: int = 0
    unknown: int = 0


@dataclass(frozen=True)
class SymbolMarketContext:
    symbol: str
    event_count: int
    impact_counts: ImpactCounts
    events: tuple[NewsEvent, ...]


@dataclass(frozen=True)
class MarketContextSnapshot:
    symbols: tuple[SymbolMarketContext, ...]


class MarketContextAggregator:
    """Builds immutable, factual summaries from validated P36 news context."""

    def aggregate(
        self,
        context: MarketContext,
        *,
        symbols: tuple[str, ...] | None = None,
    ) -> MarketContextSnapshot:
        if not isinstance(context, MarketContext):
            raise ValueError("context is invalid")
        if any(not isinstance(event, NewsEvent) for event in context.events):
            raise ValueError("context contains invalid news events")

        requested = None
        if symbols is not None:
            if not isinstance(symbols, tuple):
                raise ValueError("symbols must be a tuple")
            normalized = tuple(symbol.strip().upper() for symbol in symbols)
            if any(not symbol for symbol in normalized):
                raise ValueError("symbols must contain non-empty values")
            if len(set(normalized)) != len(normalized):
                raise ValueError("symbols must not contain duplicates")
            requested = normalized

        events = tuple(sorted(context.events, key=self._sort_key))
        available = {symbol for event in events for symbol in event.symbols}
        target_symbols = requested if requested is not None else tuple(sorted(available))
        summaries = tuple(self._summarize(symbol, events) for symbol in target_symbols)
        return MarketContextSnapshot(summaries)

    @staticmethod
    def _sort_key(event: NewsEvent) -> tuple:
        return (event.published_at, event.source, event.title, event.symbols, event.impact.value)

    @staticmethod
    def _summarize(symbol: str, events: tuple[NewsEvent, ...]) -> SymbolMarketContext:
        related = tuple(event for event in events if symbol in event.symbols)
        counts = {impact: 0 for impact in NewsImpact}
        for event in related:
            counts[event.impact] += 1
        return SymbolMarketContext(
            symbol=symbol,
            event_count=len(related),
            impact_counts=ImpactCounts(
                low=counts[NewsImpact.LOW],
                medium=counts[NewsImpact.MEDIUM],
                high=counts[NewsImpact.HIGH],
                unknown=counts[NewsImpact.UNKNOWN],
            ),
            events=related,
        )
