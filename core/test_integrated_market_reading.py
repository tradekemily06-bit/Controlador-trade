from datetime import datetime, timedelta

from core.integrated_market_reading import IntegratedMarketReader, ReadingStatus
from core.market_data import Candle


def candles_for_breakout():
    base = datetime(2026, 1, 1)
    return [
        Candle(base, 100, 105, 99, 103, 10),
        Candle(base + timedelta(minutes=5), 103, 106, 101, 105, 10),
        Candle(base + timedelta(minutes=10), 105, 110, 104, 104, 12),
    ]


def test_reader_integrates_observations_without_order_authority():
    reading = IntegratedMarketReader().read(candles_for_breakout())
    assert reading.observations
    assert reading.independent_confluences >= 2
    assert reading.status in {ReadingStatus.SUPPORTED, ReadingStatus.CONFLICTING}
    assert all(o.domain for o in reading.observations)


def test_apparent_breakout_without_follow_through_is_reassessed():
    reading = IntegratedMarketReader().read(candles_for_breakout())
    assert reading.possible_false_breakout is True
    assert any("rompimento" in q.lower() for q in reading.unanswered_questions)


def test_insufficient_market_history_fails_closed():
    base = datetime(2026, 1, 1)
    candle = Candle(base, 100, 101, 99, 100.5, 10)
    reading = IntegratedMarketReader().read([candle])
    assert reading.status is ReadingStatus.INSUFFICIENT
    assert reading.independent_confluences == 0
