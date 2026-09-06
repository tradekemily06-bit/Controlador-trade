from datetime import datetime, timedelta

import pytest

from core.replay_engine import ReplayEngine
from core.models import AnalysisResult, Signal
from core.decision_engine import FinalDecision


def make_candle(index, close=100):
    from core.market_data import Candle

    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=index),
        open=100,
        high=max(101, close + 1),
        low=99,
        close=close,
        volume=100,
    )


class FakeDecision:
    def __init__(self, decision, signal, reason):
        self.decision = decision
        self.signal = signal
        self.reason = reason


def test_replay_processes_candles_in_order():
    candles = [
        make_candle(0, 100),
        make_candle(1, 101),
        make_candle(2, 102),
    ]

    def decide(candle):
        return FakeDecision(
            FinalDecision.EXECUTAR,
            Signal.COMPRA,
            "Sinal aprovado.",
        )

    result = ReplayEngine().run(
        candles=candles,
        decision_function=decide,
    )

    assert result.total_candles == 3
    assert result.executed == 3
    assert result.blocked == 0
    assert result.waiting == 0

    assert [r.close for r in result.records] == [100, 101, 102]


def test_replay_counts_decisions():
    candles = [
        make_candle(0),
        make_candle(1),
        make_candle(2),
    ]

    decisions = iter(
        [
            FakeDecision(
                FinalDecision.EXECUTAR,
                Signal.COMPRA,
                "Executou.",
            ),
            FakeDecision(
                FinalDecision.BLOQUEAR,
                Signal.VENDA,
                "Risco.",
            ),
            FakeDecision(
                FinalDecision.AGUARDAR,
                Signal.COMPRA,
                "Aguardando.",
            ),
        ]
    )

    result = ReplayEngine().run(
        candles=candles,
        decision_function=lambda candle: next(decisions),
    )

    assert result.executed == 1
    assert result.blocked == 1
    assert result.waiting == 1


def test_replay_registers_signal_and_reason():
    candles = [make_candle(0)]

    result = ReplayEngine().run(
        candles=candles,
        decision_function=lambda candle: FakeDecision(
            FinalDecision.EXECUTAR,
            Signal.COMPRA,
            "Sinal confirmado.",
        ),
    )

    record = result.records[0]

    assert record.signal == "COMPRA"
    assert record.decision == "EXECUTAR"
    assert record.reason == "Sinal confirmado."
    assert record.close == 100


def test_replay_requires_candles():
    with pytest.raises(ValueError):
        ReplayEngine().run(
            candles=[],
            decision_function=lambda candle: None,
        )
