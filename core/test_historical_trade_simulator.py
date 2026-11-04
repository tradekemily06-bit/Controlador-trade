from datetime import datetime, timedelta

import pytest

from core.historical_trade_simulator import (
    HistoricalBacktestConfig,
    HistoricalSignal,
    HistoricalTradeSimulator,
)
from core.market_data import Candle
from core.models import Signal


def bars(*values):
    start = datetime(2026, 11, 1)
    result = []
    for index, (open_price, high, low, close) in enumerate(values):
        result.append(Candle(
            timestamp=start + timedelta(minutes=index),
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=100,
        ))
    return result


def config(**overrides):
    values = {
        "stop_distance": 0.5,
        "take_profit_distance": 1.0,
        "quantity_units": 10,
        "spread_price_units": 0.02,
        "slippage_price_units_per_side": 0.01,
        "commission_quote_per_unit_round_turn": 0.05,
        "minimum_directional_score": 80,
    }
    values.update(overrides)
    return HistoricalBacktestConfig(**values)


def signal(direction=Signal.AGUARDAR, score=0, reason="teste"):
    return HistoricalSignal(direction, score, reason)


def test_enters_only_on_next_candle_and_calculates_all_costs():
    data = bars(
        (100, 100.5, 99.5, 100),
        (100, 101, 99.8, 100.5),
        (100.5, 102, 100.2, 101.5),
    )
    result = HistoricalTradeSimulator().run(
        candles=data,
        signals=[signal(Signal.COMPRA, 85), signal(), signal()],
        config=config(),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.signal_timestamp == data[0].timestamp.isoformat()
    assert trade.entry_timestamp == data[1].timestamp.isoformat()
    assert trade.exit_timestamp == data[2].timestamp.isoformat()
    assert trade.entry_price == pytest.approx(100.02)
    assert trade.exit_reason == "TAKE_PROFIT"
    assert trade.gross_pnl_quote == pytest.approx(10.2)
    assert trade.spread_cost_quote == pytest.approx(0.2)
    assert trade.slippage_cost_quote == pytest.approx(0.2)
    assert trade.commission_quote == pytest.approx(0.5)
    assert trade.net_pnl_quote == pytest.approx(9.3)
    assert result.orders_sent is False
    assert result.execution_allowed is False
    assert result.lookahead is False


def test_when_stop_and_target_are_both_touched_stop_is_assumed_first():
    data = bars(
        (100, 100.5, 99.5, 100),
        (100, 102, 99, 100.5),
    )
    result = HistoricalTradeSimulator().run(
        candles=data,
        signals=[signal(Signal.COMPRA, 90), signal()],
        config=config(),
    )
    assert result.trades[0].exit_reason == "STOP_LOSS"
    assert result.losses == 1


def test_stop_gap_uses_worse_open_price():
    data = bars(
        (100, 100.5, 99.5, 100),
        (99, 100, 98.8, 99.2),
    )
    result = HistoricalTradeSimulator().run(
        candles=data,
        signals=[signal(Signal.COMPRA, 90), signal()],
        config=config(),
    )
    trade = result.trades[0]
    assert trade.exit_reason == "STOP_GAP"
    assert trade.exit_price == pytest.approx(98.98)


def test_short_position_uses_directional_prices():
    data = bars(
        (100, 100.5, 99.5, 100),
        (100, 100.2, 98.8, 99),
    )
    result = HistoricalTradeSimulator().run(
        candles=data,
        signals=[signal(Signal.VENDA, 90), signal()],
        config=config(),
    )
    trade = result.trades[0]
    assert trade.direction == "VENDA"
    assert trade.exit_reason == "TAKE_PROFIT"
    assert trade.net_pnl_quote > 0


def test_filters_below_threshold_and_ignores_waiting():
    data = bars(
        (100, 100.5, 99.5, 100),
        (100, 101, 99, 100),
    )
    result = HistoricalTradeSimulator().run(
        candles=data,
        signals=[signal(Signal.COMPRA, 79), signal()],
        config=config(),
    )
    assert result.filtered == 1
    assert result.candidates == 0
    assert result.trades == ()


def test_rejects_mismatched_signal_count_and_duplicate_timestamps():
    data = bars((100, 101, 99, 100), (100, 101, 99, 100))
    with pytest.raises(ValueError, match="exatamente um sinal"):
        HistoricalTradeSimulator().run(
            candles=data, signals=[signal()], config=config()
        )
    duplicate = [data[0], Candle(
        timestamp=data[0].timestamp,
        open=100, high=101, low=99, close=100, volume=1,
    )]
    with pytest.raises(ValueError, match="estritamente crescente"):
        HistoricalTradeSimulator().run(
            candles=duplicate, signals=[signal(), signal()], config=config()
        )


@pytest.mark.parametrize("field,value", [
    ("stop_distance", 0),
    ("take_profit_distance", -1),
    ("quantity_units", 0),
    ("spread_price_units", -1),
    ("slippage_price_units_per_side", float("nan")),
    ("minimum_directional_score", 69),
])
def test_rejects_invalid_configuration(field, value):
    with pytest.raises(ValueError):
        config(**{field: value})
