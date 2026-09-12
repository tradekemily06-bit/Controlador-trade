from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.models import AnalysisResult, Signal
from core.mt5_demo_analysis_service import build_ic_markets_mt5_demo_analysis_service


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 2
    TIMEFRAME_M5 = 5

    def __init__(self) -> None:
        self.initialized = 0
        self.shutdowns = 0

    def symbols_get(self):
        return (SimpleNamespace(name="BTCUSD"), SimpleNamespace(name="EURUSD"))

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol, visible=True, trade_mode=0)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=100.0, ask=100.1, last=100.05)

    def initialize(self):
        self.initialized += 1
        return True

    def account_info(self):
        return SimpleNamespace(trade_mode=self.ACCOUNT_TRADE_MODE_DEMO)

    def symbol_select(self, symbol, selected):
        return selected

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        assert timeframe == self.TIMEFRAME_M5
        assert start_pos == 1
        return [
            {"time": 1000, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "tick_volume": 10, "real_volume": 10},
            {"time": 1060, "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.8, "tick_volume": 12, "real_volume": 12},
        ]

    def shutdown(self):
        self.shutdowns += 1

    def last_error(self):
        return (0, "ok")


def test_service_construction_is_side_effect_free():
    runtime = FakeMT5()
    service = build_ic_markets_mt5_demo_analysis_service(mt5_module=runtime)

    assert callable(service)
    assert runtime.initialized == 0
    assert runtime.shutdowns == 0


def test_service_discovers_ranks_and_evaluates_demo_assets():
    runtime = FakeMT5()

    def evaluator(snapshot):
        return AnalysisResult(
            signal=Signal.COMPRA,
            score=80,
            reason="teste",
            confirmed=True,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
        )

    service = build_ic_markets_mt5_demo_analysis_service(
        mt5_module=runtime,
        timeframe="5m",
        candle_limit=2,
        analysis_limit=2,
        evaluator=evaluator,
    )
    results = service()

    assert len(results) == 2
    assert {item.result.symbol for item in results} == {"BTCUSD", "EURUSD"}
    assert all(item.result.signal is Signal.COMPRA for item in results)
    assert runtime.shutdowns == 2


def test_service_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        build_ic_markets_mt5_demo_analysis_service(candle_limit=0)
    with pytest.raises(ValueError):
        build_ic_markets_mt5_demo_analysis_service(analysis_limit=-1)
    with pytest.raises(TypeError):
        build_ic_markets_mt5_demo_analysis_service(evaluator=object())
