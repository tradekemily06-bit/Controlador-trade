from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from data.models import Candle


class MarketDataHealth(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    GAP = "GAP"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MarketDataIntegrityReport:
    health: MarketDataHealth
    candle_count: int
    expected_interval_seconds: int | None
    gap_count: int
    stale: bool
    message: str


class MarketDataIntegrity:
    """Read-only integrity checks for chronological market data."""

    def __init__(self, *, max_age_seconds: int = 300) -> None:
        if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
            raise ValueError("max_age_seconds deve ser um inteiro positivo.")
        self.max_age_seconds = max_age_seconds

    def assess(
        self,
        candles: tuple[Candle, ...] | list[Candle],
        *,
        now: datetime,
        expected_interval_seconds: int | None = None,
    ) -> MarketDataIntegrityReport:
        if not isinstance(now, datetime):
            raise ValueError("now inválido.")
        if expected_interval_seconds is not None and (
            isinstance(expected_interval_seconds, bool)
            or not isinstance(expected_interval_seconds, int)
            or expected_interval_seconds <= 0
        ):
            raise ValueError("intervalo esperado inválido.")

        items = tuple(candles)
        if not items or any(not isinstance(c, Candle) or not c.is_valid() for c in items):
            return MarketDataIntegrityReport(
                MarketDataHealth.INVALID,
                len(items),
                expected_interval_seconds,
                0,
                False,
                "dados de mercado inválidos",
            )

        timestamps = tuple(c.timestamp for c in items)
        timezone_aware = tuple(ts.tzinfo is not None and ts.utcoffset() is not None for ts in timestamps)
        now_aware = now.tzinfo is not None and now.utcoffset() is not None
        if any(aware != now_aware for aware in timezone_aware):
            return MarketDataIntegrityReport(
                MarketDataHealth.INVALID,
                len(items),
                expected_interval_seconds,
                0,
                False,
                "timezone incompatível entre candles e now",
            )
        if any(a >= b for a, b in zip(timestamps, timestamps[1:])):
            return MarketDataIntegrityReport(
                MarketDataHealth.INVALID,
                len(items),
                expected_interval_seconds,
                0,
                False,
                "timestamps fora de ordem ou duplicados",
            )
        if timestamps[-1] > now:
            return MarketDataIntegrityReport(
                MarketDataHealth.INVALID,
                len(items),
                expected_interval_seconds,
                0,
                False,
                "último candle está no futuro em relação a now",
            )

        gap_count = 0
        if expected_interval_seconds is not None:
            interval = timedelta(seconds=expected_interval_seconds)
            gap_count = sum(b - a != interval for a, b in zip(timestamps, timestamps[1:]))

        stale = (now - timestamps[-1]).total_seconds() > self.max_age_seconds
        if stale:
            return MarketDataIntegrityReport(
                MarketDataHealth.STALE,
                len(items),
                expected_interval_seconds,
                gap_count,
                True,
                "último candle está desatualizado",
            )
        if expected_interval_seconds is None:
            return MarketDataIntegrityReport(
                MarketDataHealth.UNKNOWN,
                len(items),
                None,
                gap_count,
                False,
                "timeframe sem intervalo conhecido; integridade temporal não pode ser confirmada",
            )
        if gap_count:
            return MarketDataIntegrityReport(
                MarketDataHealth.GAP,
                len(items),
                expected_interval_seconds,
                gap_count,
                False,
                "há lacunas na sequência de candles",
            )
        return MarketDataIntegrityReport(
            MarketDataHealth.HEALTHY,
            len(items),
            expected_interval_seconds,
            0,
            False,
            "dados de mercado íntegros",
        )
