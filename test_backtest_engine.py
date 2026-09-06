from datetime import datetime, timedelta

import pytest

from core.backtest_engine import BacktestEngine, TradeResult
from core.market_data import Candle
from core.models import Signal


def make_candle(index, high, low, close=100):
    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=index),
        open=100,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def test_buy_hits_take_profit():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 103, 99, 102),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0],
        signal=Signal.COMPRA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    trade = result.trades[0]

    assert trade.result == TradeResult.WIN
    assert trade.exit_price == 102
    assert trade.profit == 2
    assert result.wins == 1


def test_buy_hits_stop_loss():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 101, 97, 98),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0],
        signal=Signal.COMPRA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    trade = result.trades[0]

    assert trade.result == TradeResult.LOSS
    assert trade.exit_price == 98
    assert trade.profit == -2
    assert result.losses == 1


def test_sell_hits_take_profit():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 101, 97, 98),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0],
        signal=Signal.VENDA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    trade = result.trades[0]

    assert trade.result == TradeResult.WIN
    assert trade.exit_price == 98
    assert trade.profit == 2


def test_sell_hits_stop_loss():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 103, 99, 102),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0],
        signal=Signal.VENDA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    trade = result.trades[0]

    assert trade.result == TradeResult.LOSS
    assert trade.exit_price == 102
    assert trade.profit == -2


def test_same_candle_tp_and_sl_is_ambiguous():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 103, 97, 100),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0],
        signal=Signal.COMPRA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    trade = result.trades[0]

    assert trade.result == TradeResult.AMBOS
    assert trade.exit_price is None
    assert trade.profit == 0
    assert result.ambiguous == 1


def test_trade_can_remain_pending():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 101, 99, 100),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0],
        signal=Signal.COMPRA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    assert result.pending == 1
    assert result.trades[0].result == TradeResult.PENDENTE


def test_invalid_signal_is_rejected():
    candles = [make_candle(0, 101, 99)]

    with pytest.raises(ValueError):
        BacktestEngine().run(
            candles=candles,
            entry_indexes=[0],
            signal=Signal.AGUARDAR,
            take_profit_distance=2,
            stop_loss_distance=2,
        )


def test_invalid_distance_is_rejected():
    candles = [make_candle(0, 101, 99)]

    with pytest.raises(ValueError):
        BacktestEngine().run(
            candles=candles,
            entry_indexes=[0],
            signal=Signal.COMPRA,
            take_profit_distance=0,
            stop_loss_distance=2,
        )


def test_backtest_calculates_win_rate():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 103, 99, 102),
        make_candle(2, 101, 99, 100),
        make_candle(3, 103, 99, 102),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0, 2],
        signal=Signal.COMPRA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    assert result.wins == 2
    assert result.losses == 0
    assert result.win_rate == 100.0


def test_backtest_calculates_profit_factor():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 103, 99, 102),
        make_candle(2, 101, 99, 100),
        make_candle(3, 101, 97, 98),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0, 2],
        signal=Signal.COMPRA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    assert result.total_profit == 0
    assert result.profit_factor == 1.0


def test_backtest_calculates_max_consecutive_losses():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 101, 97, 98),
        make_candle(2, 101, 99, 100),
        make_candle(3, 101, 97, 98),
        make_candle(4, 101, 99, 100),
        make_candle(5, 103, 99, 102),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0, 2, 4],
        signal=Signal.COMPRA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    assert result.losses == 2
    assert result.wins == 1
    assert result.max_consecutive_losses == 2


def test_backtest_calculates_max_drawdown():
    candles = [
        make_candle(0, 101, 99, 100),
        make_candle(1, 103, 99, 102),
        make_candle(2, 101, 97, 98),
    ]

    result = BacktestEngine().run(
        candles=candles,
        entry_indexes=[0, 1],
        signal=Signal.COMPRA,
        take_profit_distance=2,
        stop_loss_distance=2,
    )

    assert result.total_profit == 0
    assert result.max_drawdown == 2
