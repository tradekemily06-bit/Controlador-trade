from datetime import datetime, timedelta, timezone

from core.candle_analysis_evaluator import evaluate_candle_snapshot
from core.models import Signal
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.models import Candle


def candle(open_, high, low, close, minute):
    return Candle(
        timestamp=datetime(2026, 9, 12, 12, minute, tzinfo=timezone.utc),
        open=open_, high=high, low=low, close=close, volume=100,
    )


def snapshot(candles):
    return BrokerMarketDataSnapshot(
        symbol="BTCUSD", timeframe="5m", candles=tuple(candles),
        source="IC_MARKETS_MT5_DEMO",
        received_at=datetime.now(timezone.utc),
    )


def test_bullish_confirmed_candle_can_produce_buy_signal():
    result = evaluate_candle_snapshot(snapshot([
        candle(100, 103, 99, 102, 0),
        candle(102, 108, 101, 107, 5),
    ]))
    assert result.signal is Signal.COMPRA
    assert result.confirmed is True
    assert result.symbol == "BTCUSD"
    assert result.timeframe == "5m"


def test_bearish_confirmed_candle_can_produce_sell_signal():
    result = evaluate_candle_snapshot(snapshot([
        candle(100, 101, 97, 98, 0),
        candle(98, 99, 92, 93, 5),
    ]))
    assert result.signal is Signal.VENDA
    assert result.confirmed is True


def test_weak_or_unconfirmed_candle_stays_wait():
    result = evaluate_candle_snapshot(snapshot([
        candle(100, 101, 99, 100.2, 0),
    ]))
    assert result.signal is Signal.AGUARDAR
    assert result.confirmed is False


def test_empty_snapshot_stays_wait():
    result = evaluate_candle_snapshot(snapshot([]))
    assert result.signal is Signal.AGUARDAR
    assert result.confirmed is False
