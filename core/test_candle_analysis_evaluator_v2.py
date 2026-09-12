from datetime import datetime, timezone
from core.candle_analysis_evaluator import evaluate_candle_snapshot
from core.models import Signal
from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.models import Candle

def c(o,h,l,cl,m):
    return Candle(datetime(2026,9,12,12,m,tzinfo=timezone.utc),o,h,l,cl,100)

def s(cs):
    return BrokerMarketDataSnapshot('BTCUSD','5m',tuple(cs),'IC_MARKETS_MT5_DEMO',datetime.now(timezone.utc))

def test_buy():
    r=evaluate_candle_snapshot(s([c(100,103,99,102,0),c(102,108,101,107,5)]))
    assert r.signal is Signal.COMPRA and r.confirmed

def test_sell():
    r=evaluate_candle_snapshot(s([c(100,101,97,98,0),c(98,99,92,93,5)]))
    assert r.signal is Signal.VENDA and r.confirmed

def test_wait_without_confirmation():
    r=evaluate_candle_snapshot(s([c(100,101,99,100.2,0)]))
    assert r.signal is Signal.AGUARDAR and not r.confirmed

def test_empty_wait():
    r=evaluate_candle_snapshot(s([]))
    assert r.signal is Signal.AGUARDAR
