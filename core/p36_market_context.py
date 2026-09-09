from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Protocol


class NewsImpact(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NewsEvent:
    published_at: datetime
    title: str
    source: str
    symbols: tuple[str, ...] = ()
    impact: NewsImpact = NewsImpact.UNKNOWN

    def __post_init__(self) -> None:
        if not isinstance(self.published_at, datetime) or self.published_at.tzinfo is None:
            raise ValueError("published_at must be timezone-aware")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("title must be non-empty")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be non-empty")
        if not isinstance(self.impact, NewsImpact):
            raise ValueError("impact is invalid")
        normalized = tuple(symbol.strip().upper() for symbol in self.symbols)
        if any(not symbol for symbol in normalized):
            raise ValueError("symbols must contain non-empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("symbols must not contain duplicates")
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "source", self.source.strip())
        object.__setattr__(self, "symbols", normalized)


@dataclass(frozen=True)
class MarketContext:
    events: tuple[NewsEvent, ...]


class NewsProvider(Protocol):
    def fetch(self) -> Iterable[NewsEvent]:
        ...


class MarketContextFeed:
    """Validates and deterministically organizes market-news context."""

    def __init__(self, provider: NewsProvider) -> None:
        if provider is None:
            raise ValueError("provider is required")
        self._provider = provider

    def fetch(self) -> MarketContext:
        raw = tuple(self._provider.fetch())
        if any(not isinstance(event, NewsEvent) for event in raw):
            raise ValueError("provider returned invalid news events")
        return MarketContext(tuple(sorted(raw, key=self._sort_key)))

    @staticmethod
    def _sort_key(event: NewsEvent) -> tuple[datetime, str, str]:
        return (event.published_at, event.source, event.title)

    def filter(
        self,
        context: MarketContext,
        *,
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> MarketContext:
        if not isinstance(context, MarketContext):
            raise ValueError("context is invalid")
        if symbol is not None and (not isinstance(symbol, str) or not symbol.strip()):
            raise ValueError("symbol must be non-empty")
        for boundary in (start, end):
            if boundary is not None and (
                not isinstance(boundary, datetime) or boundary.tzinfo is None
            ):
                raise ValueError("time boundaries must be timezone-aware")
        if start is not None and end is not None and start > end:
            raise ValueError("start must not be after end")

        normalized_symbol = symbol.strip().upper() if symbol is not None else None
        events = context.events
        if normalized_symbol is not None:
            events = tuple(event for event in events if normalized_symbol in event.symbols)
        if start is not None:
            events = tuple(event for event in events if event.published_at >= start)
        if end is not None:
            events = tuple(event for event in events if event.published_at <= end)
        return MarketContext(events)
