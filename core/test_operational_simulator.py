from datetime import datetime, timedelta

import pytest

from .market_data import Candle
from .models import Signal
from .operational_simulator import (
    OperationalSimulator,
    SimulationDecision,
    SimulationStage,
)


def candles(count=4):
    start = datetime(2026, 1, 1)
    return [
        Candle(
            timestamp=start + timedelta(minutes=i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100 + i,
            volume=1,
        )
        for i in range(count)
    ]


def test_uses_only_current_and_past_candles():
    seen_lengths = []

    def decide(history):
        seen_lengths.append(len(history))
        return SimulationDecision(Signal.AGUARDAR, "AGUARDAR", "sem sinal")

    result = OperationalSimulator().run(candles=candles(), decision_function=decide)

    assert seen_lengths == [1, 2, 3, 4]
    assert result.total_candles == 4
    assert result.waiting == 4
    assert result.signals == 0
    assert result.executed == 0


def test_separates_waiting_blocked_and_executed():
    def decide(history):
        index = len(history) - 1
        if index == 0:
            return SimulationDecision(Signal.AGUARDAR, "AGUARDAR", "aguardar")
        if index == 1:
            return SimulationDecision(Signal.COMPRA, "BLOQUEAR", "risco bloqueou")
        return SimulationDecision(Signal.VENDA, "EXECUTAR", "aprovada")

    result = OperationalSimulator().run(candles=candles(), decision_function=decide)

    assert result.waiting == 1
    assert result.blocked == 1
    assert result.approved == 2
    assert result.executed == 2
    assert result.records[0].stage == SimulationStage.WAITING
    assert result.records[1].stage == SimulationStage.BLOCKED
    assert result.records[2].stage == SimulationStage.EXECUTED


def test_aguardar_decision_is_waiting_even_with_signal():
    def decide(history):
        return SimulationDecision(Signal.COMPRA, "AGUARDAR", "contexto incompatível")

    result = OperationalSimulator().run(candles=candles(1), decision_function=decide)

    assert result.waiting == 1
    assert result.blocked == 0
    assert result.executed == 0
    assert result.records[0].stage == SimulationStage.WAITING


def test_preserves_explainability():
    def decide(history):
        return SimulationDecision(Signal.COMPRA, "EXECUTAR", f"histórico={len(history)}")

    result = OperationalSimulator().run(candles=candles(2), decision_function=decide)

    assert [record.reason for record in result.records] == ["histórico=1", "histórico=2"]
    assert [record.index for record in result.records] == [0, 1]


def test_rejects_empty_data():
    with pytest.raises(ValueError, match="candles"):
        OperationalSimulator().run(candles=[], decision_function=lambda history: None)


def test_rejects_invalid_decision_result():
    with pytest.raises(TypeError, match="SimulationDecision"):
        OperationalSimulator().run(candles=candles(1), decision_function=lambda history: None)


def test_rejects_unknown_decision():
    with pytest.raises(ValueError, match="decisão inválida"):
        OperationalSimulator().run(
            candles=candles(1),
            decision_function=lambda history: SimulationDecision(
                Signal.COMPRA, "DESCONHECIDA", "teste"
            ),
        )


def test_rejects_out_of_order_candles():
    data = candles(3)
    data[2] = Candle(
        timestamp=data[0].timestamp - timedelta(minutes=1),
        open=102,
        high=103,
        low=101,
        close=102,
        volume=1,
    )

    with pytest.raises(ValueError, match="ordem cronológica"):
        OperationalSimulator().run(
            candles=data,
            decision_function=lambda history: SimulationDecision(
                Signal.AGUARDAR, "AGUARDAR", "teste"
            ),
        )


def test_exposes_laboratory_metrics():
    def decide(history):
        index = len(history) - 1
        if index == 0:
            return SimulationDecision(Signal.AGUARDAR, "AGUARDAR", "aguardar")
        if index == 1:
            return SimulationDecision(Signal.COMPRA, "BLOQUEAR", "bloqueada")
        return SimulationDecision(Signal.VENDA, "EXECUTAR", "executada")

    result = OperationalSimulator().run(candles=candles(), decision_function=decide)
    metrics = result.metrics

    assert metrics.total_candles == 4
    assert metrics.buy_signals == 1
    assert metrics.sell_signals == 2
    assert metrics.waiting_signals == 1
    assert metrics.approved == 2
    assert metrics.blocked == 1
    assert metrics.waiting == 1
    assert metrics.executed == 2
    assert metrics.signal_rate == 0.75
    assert metrics.approval_rate == 0.5
    assert metrics.execution_rate == 0.5
