"""Normalization boundary for indicator readings from MT5 or trusted external providers.

Provider adapters must perform their own transport/authentication and normalize raw
provider payloads here. Readings remain evidence-only and cannot authorize execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Mapping, Protocol


class IndicatorSourceKind(str, Enum):
    MT5_NATIVE = "MT5_NATIVE"
    MT5_CUSTOM = "MT5_CUSTOM"
    EXTERNAL_SITE = "EXTERNAL_SITE"
    CONTROLADOR_CALCULATED = "CONTROLADOR_CALCULATED"


@dataclass(frozen=True)
class ExternalIndicatorReading:
    provider: str
    source_kind: IndicatorSourceKind
    symbol: str
    timeframe: str
    observed_at: datetime
    candle_timestamp: datetime
    values: Mapping[str, float]
    bias: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, IndicatorSourceKind):
            raise ValueError("source_kind must be a supported IndicatorSourceKind")
        if not isinstance(self.values, Mapping):
            raise ValueError("values must be a mapping of indicator names to numbers")
        for name in ("provider", "symbol", "timeframe"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        for name in ("observed_at", "candle_timestamp"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.candle_timestamp > self.observed_at:
            raise ValueError("indicator candle timestamp cannot be after observation time")
        if not self.values:
            raise ValueError("at least one indicator value is required")
        for name, value in self.values.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("indicator names must be non-empty")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError(f"indicator {name!r} must be finite numeric data")
        if self.bias is not None and self.bias not in {"BULLISH", "BEARISH", "MIXED", "UNAVAILABLE"}:
            raise ValueError("bias is not recognized")


class IndicatorReadingProvider(Protocol):
    """Adapter contract for MT5 native/custom indicators or external services."""

    def read(
        self,
        *,
        symbol: str,
        timeframe: str,
        now: datetime | None = None,
    ) -> ExternalIndicatorReading | None:
        ...


def is_fresh_indicator_reading(
    reading: ExternalIndicatorReading,
    *,
    now: datetime,
    max_age_seconds: int = 120,
) -> bool:
    """Reject stale/future-dated readings instead of silently trusting them."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds cannot be negative")
    age = (now.astimezone(timezone.utc) - reading.observed_at.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= max_age_seconds
