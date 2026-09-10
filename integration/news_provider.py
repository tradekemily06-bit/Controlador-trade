from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    published_at: str | None = None
    url: str | None = None

class NewsProvider(Protocol):
    def latest(self, *, symbol: str | None = None, limit: int = 10) -> list[NewsItem]: ...

class UnconfiguredNewsProvider:
    """Fail-closed provider: never fabricates or claims live news."""
    def latest(self, *, symbol: str | None = None, limit: int = 10) -> list[NewsItem]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        return []
