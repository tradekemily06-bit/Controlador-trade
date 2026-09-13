from datetime import datetime, timedelta, timezone

from core.p122_broker_market_data import BrokerMarketDataSnapshot
from core.p23_market_data_integrity import MarketDataHealth
from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from data.models import Candle


def snapshot(timeframe: str = "5m", minutes: tuple[int, ...] = (0, 5, 10)) -> BrokerMarketDataSnapshot:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(Candle(base + timedelta(minutes=i), 100, 101, 99, 100, 1) for i in minutes)
    return BrokerMarketDataSnapshot("EURUSD", timeframe, candles, "IC_MARKETS_MT5_DEMO", base + timedelta(minutes=10))


def test_healthy_snapshot_is_safe_for_analysis():
    report = MarketDataRuntimeIntegrity().assess(snapshot(), now=datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc))
    assert report.health is MarketDataHealth.HEALTHY
    assert report.safe_for_analysis is True
    assert report.to_dict()["source"] == "IC_MARKETS_MT5_DEMO"


def test_gap_snapshot_is_not_safe_for_analysis():
    report = MarketDataRuntimeIntegrity().assess(
        snapshot(minutes=(0, 10)),
        now=datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc),
    )
    assert report.health is MarketDataHealth.GAP
    assert report.safe_for_analysis is False
    assert report.gap_count == 1


def test_unknown_timeframe_does_not_invent_interval():
    report = MarketDataRuntimeIntegrity().assess(
        snapshot(timeframe="unknown"),
        now=datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc),
    )
    assert report.health is MarketDataHealth.HEALTHY
