from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity, MarketDataRuntimeReport
from core.p122_broker_market_data import BrokerMarketDataSnapshot


@dataclass
class MarketDataRuntimeState:
    """Provider-neutral, read-only market-data state used by operational observability."""

    integrity: MarketDataRuntimeIntegrity
    report: MarketDataRuntimeReport | None = None

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
        self.report = report
        return report

    def status(self) -> dict[str, object]:
        if self.report is None:
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
