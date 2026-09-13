from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.p122_broker_market_data import BrokerMarketDataSnapshot
from core.p23_market_data_integrity import MarketDataHealth, MarketDataIntegrity, MarketDataIntegrityReport


_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


@dataclass(frozen=True)
class MarketDataRuntimeReport:
    source: str
    symbol: str
    timeframe: str
    health: MarketDataHealth
    candle_count: int
    gap_count: int
    stale: bool
    message: str

    @property
    def safe_for_analysis(self) -> bool:
        return self.health is MarketDataHealth.HEALTHY

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "health": self.health.value,
            "candle_count": self.candle_count,
            "gap_count": self.gap_count,
            "stale": self.stale,
            "message": self.message,
            "safe_for_analysis": self.safe_for_analysis,
        }


class MarketDataRuntimeIntegrity:
    """Connects the broker-neutral snapshot contract to P23 integrity checks.

    This layer is deliberately read-only: it does not fetch data, place orders,
    retry providers, or manufacture a healthy state when the source is absent.
    """

    def __init__(self, integrity: MarketDataIntegrity | None = None) -> None:
        self.integrity = integrity or MarketDataIntegrity()

    def assess(
        self,
        snapshot: BrokerMarketDataSnapshot,
        *,
        now: datetime,
        expected_interval_seconds: int | None = None,
    ) -> MarketDataRuntimeReport:
        if not isinstance(snapshot, BrokerMarketDataSnapshot):
            raise TypeError("snapshot deve ser BrokerMarketDataSnapshot")
        if not isinstance(now, datetime):
            raise ValueError("now inválido")

        interval = expected_interval_seconds
        if interval is None:
            interval = _TIMEFRAME_SECONDS.get(snapshot.timeframe.strip().lower())

        report: MarketDataIntegrityReport = self.integrity.assess(
            snapshot.candles,
            now=now,
            expected_interval_seconds=interval,
        )
        return MarketDataRuntimeReport(
            source=snapshot.source,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            health=report.health,
            candle_count=report.candle_count,
            gap_count=report.gap_count,
            stale=report.stale,
            message=report.message,
        )
