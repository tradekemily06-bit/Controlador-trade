from datetime import datetime, timedelta, timezone

import pytest

from core.models import Signal
from core.operation_memory import OperationMemory, OperationMemoryRecord
from core.operational_analytics import AnalyticsSnapshot, OperationalAnalytics


def record(index, signal, result, decision="EXECUTAR", quality="FORTE"):
    return OperationMemoryRecord(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index),
        signal=signal,
        score=80.0,
        decision=decision,
        reason="teste",
        result=result,
        symbol="TEST",
        timeframe="1m",
        quality_score=90.0,
        quality_level=quality,
        entry_conditions=("fechamento",),
    )


def test_snapshot_aggregates_results_direction_quality_and_decisions():
    memory = OperationMemory()
    memory.append(record(1, Signal.COMPRA, "WIN", quality="FORTE"))
    memory.append(record(2, Signal.COMPRA, "LOSS", quality="FORTE"))
    memory.append(record(3, Signal.VENDA, "WIN", quality="MODERADA"))
    memory.append(record(4, Signal.VENDA, "AMBOS", decision="BLOQUEAR", quality="MODERADA"))
    memory.append(record(5, Signal.AGUARDAR, "PENDENTE", decision="AGUARDAR"))

    snapshot = OperationalAnalytics(memory).snapshot()

    assert isinstance(snapshot, AnalyticsSnapshot)
    assert snapshot.total == 5
    assert snapshot.completed == 3
    assert snapshot.pending == 1
    assert snapshot.ambiguous == 1
    assert snapshot.wins == 2
    assert snapshot.losses == 1
    assert snapshot.win_rate == pytest.approx(2 / 3)
    assert snapshot.direction[Signal.COMPRA.value]["wins"] == 1
    assert snapshot.direction[Signal.VENDA.value]["wins"] == 1
    assert snapshot.quality["FORTE"]["total"] == 2
    assert snapshot.quality["MODERADA"]["total"] == 1
    assert snapshot.decision_distribution == {
        "EXECUTAR": 3,
        "BLOQUEAR": 1,
        "AGUARDAR": 1,
    }


def test_snapshot_respects_inclusive_period():
    memory = OperationMemory()
    memory.append(record(1, Signal.COMPRA, "WIN"))
    memory.append(record(2, Signal.COMPRA, "LOSS"))
    memory.append(record(3, Signal.VENDA, "WIN"))

    start = datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc)
    snapshot = OperationalAnalytics(memory).snapshot(start=start, end=end)

    assert snapshot.total == 2
    assert snapshot.wins == 1
    assert snapshot.losses == 1


def test_invalid_period_is_rejected():
    memory = OperationMemory()
    analytics = OperationalAnalytics(memory)
    start = datetime(2026, 1, 2, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="posterior"):
        analytics.records(start=start, end=end)


def test_analytics_does_not_mutate_memory():
    memory = OperationMemory()
    memory.append(record(1, Signal.COMPRA, "LOSS"))
    before = memory.records()

    snapshot = OperationalAnalytics(memory).snapshot()

    assert snapshot.losses == 1
    assert memory.records() == before
