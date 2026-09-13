from datetime import datetime, timedelta, timezone

from core.market_data_runtime_integrity import MarketDataRuntimeIntegrity
from core.market_data_runtime_state import MarketDataRuntimeState
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.models import Candle


def snapshot(*minutes: int, timeframe: str = "1m") -> BrokerMarketDataSnapshot:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = tuple(
        Candle(base + timedelta(minutes=minute), 100, 101, 99, 100, 1)
        for minute in minutes
    )
    return BrokerMarketDataSnapshot(
        symbol="EURUSD",
        timeframe=timeframe,
        candles=candles,
        source="TEST_PROVIDER",
        received_at=base,
    )


def test_empty_runtime_is_not_connected_and_not_safe() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    status = state.status()
    assert status["health"] == "NOT_CONNECTED"
    assert status["safe_for_analysis"] is False


def test_healthy_snapshot_becomes_safe_for_analysis() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    report = state.update(
        snapshot(0, 1, 2),
        now=datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc),
        expected_interval_seconds=60,
    )
    assert report.safe_for_analysis is True
    assert state.status()["health"] == "HEALTHY"
    assert state.status()["source"] == "TEST_PROVIDER"


def test_gap_snapshot_is_not_safe() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    report = state.update(
        snapshot(0, 2),
        now=datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc),
        expected_interval_seconds=60,
    )
    assert report.health.value == "GAP"
    assert report.safe_for_analysis is False
    assert state.status()["gap_count"] == 1
