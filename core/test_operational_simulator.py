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
