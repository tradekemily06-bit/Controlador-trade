from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity, MarketDataRuntimeReport
from core.p122_broker_market_data import BrokerMarketDataSnapshot


@dataclass
class MarketDataRuntimeState:
    """Provider-neutral market-data state used by operational observability."""

    integrity: MarketDataRuntimeIntegrity
    report: MarketDataRuntimeReport | None = None
    unavailable_reason: str | None = None

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
        self.unavailable_reason = None
        return report

    def invalidate(self, reason: str) -> None:
        """Clear any previously healthy snapshot when the latest read fails."""
        message = str(reason).strip() if isinstance(reason, str) else ""
        self.report = None
        self.unavailable_reason = message or "ciclo de mercado falhou; dados atuais indisponíveis"

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
                "message": self.unavailable_reason or "nenhum snapshot de mercado foi recebido pelo runtime",
            }
        return self.report.to_dict()
