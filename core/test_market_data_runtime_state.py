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
        now=datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc),
        expected_interval_seconds=60,
    )
    assert report.health.value == "GAP"
    assert report.safe_for_analysis is False
    assert state.status()["gap_count"] == 1


def test_failed_latest_cycle_invalidates_previously_healthy_snapshot() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    state.update(
        snapshot(0, 1, 2),
        now=datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc),
        expected_interval_seconds=60,
    )
    assert state.status()["health"] == "HEALTHY"

    state.invalidate("ciclo de análise indisponível: MT5MarketDataError")
    status = state.status()
    assert status["health"] == "NOT_CONNECTED"
    assert status["safe_for_analysis"] is False
    assert status["source"] is None
    assert status["message"] == "ciclo de análise indisponível: MT5MarketDataError"


def test_successful_update_clears_previous_unavailable_reason() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    state.invalidate("falha de teste")
    state.update(
        snapshot(0, 1, 2),
        now=datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc),
        expected_interval_seconds=60,
    )
    assert state.status()["health"] == "HEALTHY"
    assert "message" in state.status()
    assert state.status()["source"] == "TEST_PROVIDER"


def test_freshness_uses_completed_bar_boundary_for_five_minute_candles() -> None:
    state = MarketDataRuntimeState(MarketDataRuntimeIntegrity())
    report = state.update(
        snapshot(0, timeframe="5m"),
        now=datetime(2026, 1, 1, 0, 9, tzinfo=timezone.utc),
    )
    assert report.health.value == "HEALTHY"
    assert report.safe_for_analysis is True

    report = state.update(
        snapshot(0, timeframe="5m"),
        now=datetime(2026, 1, 1, 0, 10, 1, tzinfo=timezone.utc),
    )
    assert report.health.value == "STALE"
    assert report.safe_for_analysis is False
