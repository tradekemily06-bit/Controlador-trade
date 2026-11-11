from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from data.models import Candle
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from core.historical_trade_simulator import HistoricalBacktestConfig, HistoricalSignal, HistoricalTradeSimulator
from core.models import Signal


def _service_with_history(candles):
    service = object.__new__(ConfiguredEcosystemService)
    service.execution_provider = "ic_markets_mt5_demo"
    service.mt5_market_adapter = SimpleNamespace(
        fetch_market_data=lambda _request: tuple(candles)
    )
    return service


def _valid_candles():
    start = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    return [
        Candle(start, 100.0, 102.0, 99.0, 101.0, 10.0),
        Candle(start + timedelta(minutes=5), 101.0, 103.0, 100.0, 102.0, 12.0),
    ]


@pytest.mark.parametrize("method_name", ["replay_mt5_history", "simulate_mt5_signal_scenario"])
def test_historical_tools_reject_duplicate_candle_timestamps(method_name):
    candles = _valid_candles()
    candles[1] = Candle(
        candles[0].timestamp, 101.0, 103.0, 100.0, 102.0, 12.0
    )
    service = _service_with_history(candles)
    method = getattr(service, method_name)

    with pytest.raises(RuntimeError, match="timestamps duplicados"):
        if method_name == "replay_mt5_history":
            method(symbol="EURUSD", timeframe="5m", limit=100)
        else:
            method(symbol="EURUSD", timeframe="5m", limit=100)


@pytest.mark.parametrize("method_name", ["replay_mt5_history", "simulate_mt5_signal_scenario"])
def test_historical_tools_reject_invalid_ohlc_candles(method_name):
    candles = _valid_candles()
    candles[1] = Candle(
        candles[1].timestamp, 101.0, 99.0, 98.0, 102.0, 12.0
    )
    service = _service_with_history(candles)
    method = getattr(service, method_name)

    with pytest.raises(RuntimeError, match="candle"):
        if method_name == "replay_mt5_history":
            method(symbol="EURUSD", timeframe="5m", limit=100)
        else:
            method(symbol="EURUSD", timeframe="5m", limit=100)

@pytest.mark.parametrize("method_name", ["replay_mt5_history", "simulate_mt5_signal_scenario"])
def test_historical_tools_reject_zero_price_ohlc_candles(method_name):
    candles = _valid_candles()
    candles[1] = Candle(
        candles[1].timestamp, 0.0, 103.0, 0.0, 102.0, 12.0
    )
    service = _service_with_history(candles)
    method = getattr(service, method_name)

    with pytest.raises(RuntimeError, match="candle inválido|OHLC inválido"):
        method(symbol="EURUSD", timeframe="5m", limit=100)


def _valid_backtest_history():
    start = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    return [
        Candle(
            start + timedelta(minutes=5 * index),
            100.0 + index * 0.1,
            101.0 + index * 0.1,
            99.0 + index * 0.1,
            100.5 + index * 0.1,
            10.0,
        )
        for index in range(20)
    ]


def _run_backtest(service):
    return service.run_mt5_historical_backtest(
        symbol="EURUSD",
        timeframe="5m",
        limit=20,
        stop_distance=0.001,
        take_profit_distance=0.002,
        quantity_units=1000,
        contract_multiplier=1,
        spread_price_units=0.0001,
        slippage_price_units_per_side=0.00005,
        commission_quote_per_unit_round_turn=0.00001,
        minimum_directional_score=80,
    )


def test_historical_backtest_rejects_duplicate_candle_timestamps():
    candles = _valid_backtest_history()
    candles[10] = Candle(
        candles[9].timestamp, 101.0, 102.0, 100.0, 101.5, 10.0
    )
    service = _service_with_history(candles)

    with pytest.raises(RuntimeError, match="timestamps repetidos"):
        _run_backtest(service)


def test_historical_backtest_rejects_zero_price_ohlc_candles():
    candles = _valid_backtest_history()
    candles[10] = Candle(
        candles[10].timestamp, 0.0, 102.0, 0.0, 101.5, 10.0
    )
    service = _service_with_history(candles)

    with pytest.raises(RuntimeError, match="candle inválido"):
        _run_backtest(service)


def test_historical_backtest_reports_friction_once_and_reconciles_net_pnl():
    start = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    candles = [
        Candle(start, 100.0, 100.5, 99.5, 100.2, 10.0),
        Candle(start + timedelta(minutes=5), 100.0, 100.5, 99.5, 100.2, 10.0),
        Candle(start + timedelta(minutes=10), 100.2, 102.0, 100.0, 101.5, 10.0),
    ]
    signals = [
        HistoricalSignal(Signal.COMPRA, 80.0, "compra confirmada"),
        HistoricalSignal(Signal.AGUARDAR, 0.0, "aguardar"),
        HistoricalSignal(Signal.AGUARDAR, 0.0, "aguardar"),
    ]
    config = HistoricalBacktestConfig(
        stop_distance=1.0,
        take_profit_distance=1.0,
        quantity_units=1.0,
        contract_multiplier=1.0,
        spread_price_units=0.1,
        slippage_price_units_per_side=0.05,
        commission_quote_per_unit_round_turn=0.05,
        minimum_directional_score=80.0,
    )

    result = HistoricalTradeSimulator().run(
        candles=candles,
        signals=signals,
        config=config,
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "TAKE_PROFIT"
    assert trade.gross_pnl_quote == pytest.approx(1.1)
    assert trade.spread_cost_quote == pytest.approx(0.1)
    assert trade.slippage_cost_quote == pytest.approx(0.1)
    assert trade.commission_quote == pytest.approx(0.05)
    assert trade.net_pnl_quote == pytest.approx(0.85)
    assert result.gross_pnl_quote - result.total_costs_quote == pytest.approx(result.net_pnl_quote)
