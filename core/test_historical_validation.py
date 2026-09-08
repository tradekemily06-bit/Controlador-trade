from datetime import datetime, timedelta

import pytest

from core.backtest_engine import TradeResult
from core.decision_engine import DecisionResult, FinalDecision
from core.historical_validation import HistoricalValidationEngine
from core.models import Signal
from data.models import Candle


def candles(*rows):
    start = datetime(2026, 1, 1)
    return [
        Candle(
            timestamp=start + timedelta(minutes=index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )
        for index, (open_, high, low, close, volume) in enumerate(rows)
    ]


def decision(decision, signal, reason="teste"):
    return DecisionResult(decision=decision, signal=signal, reason=reason)


def test_replays_only_history_available_at_each_candle_and_preserves_decisions():
    data = candles(
        (100, 100, 99, 100, 1),
        (100, 101, 99, 100, 1),
        (100, 101, 99, 100, 1),
    )
    seen_lengths = []

    def decide(history):
        seen_lengths.append(len(history))
        assert len(history) <= 3
        if len(history) == 1:
            return decision(FinalDecision.EXECUTAR, Signal.COMPRA)
        if len(history) == 2:
            return decision(FinalDecision.BLOQUEAR, Signal.VENDA, "risco")
        return decision(FinalDecision.AGUARDAR, Signal.AGUARDAR, "sem oportunidade")

    result = HistoricalValidationEngine().run(
        candles=data,
        decision_function=decide,
        take_profit_distance=1,
        stop_loss_distance=1,
    )

    assert seen_lengths == [1, 2, 3]
    assert [record.decision for record in result.records] == [
        FinalDecision.EXECUTAR,
        FinalDecision.BLOQUEAR,
        FinalDecision.AGUARDAR,
    ]
    assert result.executed == 1
    assert result.blocked == 1
    assert result.waiting == 1


def test_executes_mixed_buy_and_sell_and_evaluates_outcomes():
    data = candles(
        (100, 100, 99, 100, 1),
        (100, 100, 99, 100, 1),
        (100, 100, 99, 100, 1),
        (100, 100, 99, 100, 1),
    )

    def decide(history):
        if len(history) == 1:
            return decision(FinalDecision.EXECUTAR, Signal.COMPRA)
        if len(history) == 2:
            return decision(FinalDecision.EXECUTAR, Signal.VENDA)
        return decision(FinalDecision.AGUARDAR, Signal.AGUARDAR)

    result = HistoricalValidationEngine().run(
        candles=data,
        decision_function=decide,
        take_profit_distance=1,
        stop_loss_distance=1,
    )

    assert result.executed == 2
    assert result.backtest.total_trades == 2
    assert [trade.signal for trade in result.backtest.trades] == [
        Signal.COMPRA,
        Signal.VENDA,
    ]
    assert result.backtest.trades[0].result == TradeResult.PENDENTE
    assert result.backtest.trades[1].result == TradeResult.PENDENTE


def test_preserves_ambiguous_and_pending_results():
    data = candles(
        (100, 100, 100, 100, 1),
        (100, 102, 98, 100, 1),
        (100, 100, 100, 100, 1),
    )

    def decide(history):
        return decision(FinalDecision.EXECUTAR, Signal.COMPRA)

    result = HistoricalValidationEngine().run(
        candles=data,
        decision_function=decide,
        take_profit_distance=1,
        stop_loss_distance=1,
        min_history=1,
    )

    assert result.backtest.trades[0].result == TradeResult.AMBOS
    assert result.backtest.trades[-1].result == TradeResult.PENDENTE


def test_rejects_non_chronological_or_duplicate_timestamps():
    start = datetime(2026, 1, 1)
    data = [
        Candle(start, 100, 101, 99, 100, 1),
        Candle(start, 101, 102, 100, 101, 1),
    ]
    data[1] = Candle(start, 101, 102, 100, 101, 1)

    with pytest.raises(ValueError, match="ordem cronológica"):
        HistoricalValidationEngine().run(
            candles=data,
            decision_function=lambda history: decision(
                FinalDecision.AGUARDAR, Signal.AGUARDAR
            ),
            take_profit_distance=1,
            stop_loss_distance=1,
        )


def test_rejects_invalid_history_configuration_and_invalid_decision_result():
    data = candles((100, 101, 99, 100, 1))

    with pytest.raises(ValueError, match="min_history"):
        HistoricalValidationEngine().run(
            candles=data,
            decision_function=lambda history: decision(
                FinalDecision.AGUARDAR, Signal.AGUARDAR
            ),
            take_profit_distance=1,
            stop_loss_distance=1,
            min_history=2,
        )

    with pytest.raises(ValueError, match="DecisionResult"):
        HistoricalValidationEngine().run(
            candles=data,
            decision_function=lambda history: object(),
            take_profit_distance=1,
            stop_loss_distance=1,
        )


def test_rejects_executar_with_waiting_signal():
    data = candles((100, 101, 99, 100, 1))

    with pytest.raises(ValueError, match="EXECUTAR exige"):
        HistoricalValidationEngine().run(
            candles=data,
            decision_function=lambda history: decision(
                FinalDecision.EXECUTAR, Signal.AGUARDAR
            ),
            take_profit_distance=1,
            stop_loss_distance=1,
        )
