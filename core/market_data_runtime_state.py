from __future__ import annotations

from dataclasses import dataclass, field
import threading
from datetime import datetime

from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity, MarketDataRuntimeReport
from core.p23_market_data_integrity import MarketDataHealth
from core.p122_broker_market_data import BrokerMarketDataSnapshot


@dataclass
class MarketDataRuntimeState:
    """Provider-neutral, read-only market-data state used by operational observability."""

    integrity: MarketDataRuntimeIntegrity
    report: MarketDataRuntimeReport | None = None
    snapshot: BrokerMarketDataSnapshot | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def update(
        self,
        snapshot: BrokerMarketDataSnapshot,
        *,
        now: datetime,
        expected_interval_seconds: int | None = None,
    ) -> MarketDataRuntimeReport:
        report = self.integrity.assess(
            snapshot,
            now=now,
            expected_interval_seconds=expected_interval_seconds,
        )
        with self._lock:
            self.snapshot = snapshot
            self.report = report
        return report

    def invalidate(self, *, source: str, symbol: str, timeframe: str, message: str) -> None:
        """Fail closed when the provider cannot refresh the authoritative snapshot."""
        with self._lock:
            previous_count = self.report.candle_count if self.report is not None else 0
            self.report = MarketDataRuntimeReport(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                health=MarketDataHealth.UNKNOWN,
                candle_count=previous_count,
                gap_count=0,
                stale=True,
                message=message,
            )

    def validated_snapshot(self, *, symbol: str, timeframe: str) -> BrokerMarketDataSnapshot | None:
        """Return the same validated snapshot represented by the current healthy report."""
        with self._lock:
            report = self.report
            snapshot = self.snapshot
            if report is None or snapshot is None or not report.safe_for_analysis:
                return None
            if report.symbol != symbol or report.timeframe != timeframe:
                return None
            return snapshot

    def validated_snapshot_for_symbol(self, *, symbol: str) -> BrokerMarketDataSnapshot | None:
        """Return the current healthy snapshot when it matches the execution symbol."""
        with self._lock:
            report = self.report
            snapshot = self.snapshot
            if report is None or snapshot is None or not report.safe_for_analysis:
                return None
            if report.symbol != symbol or snapshot.symbol != symbol:
                return None
            return snapshot
    def status(self) -> dict[str, object]:
        with self._lock:
            report = self.report
        if report is None:
            return {
                "health": "NOT_CONNECTED",
                "safe_for_analysis": False,
                "source": None,
                "symbol": None,
                "timeframe": None,
                "candle_count": None,
                "gap_count": None,
                "stale": None,
                "message": "nenhum snapshot de mercado foi recebido pelo runtime",
            }
        return self.report.to_dict()
