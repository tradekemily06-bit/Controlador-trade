from datetime import datetime, timezone

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.models import Signal
from core.operation_memory_store import OperationMemoryStore
from core.persistent_operational_recorder import PersistentOperationalRecorder


def snapshot() -> DecisionSnapshot:
    return DecisionSnapshot(
        signal="COMPRA",
        analysis_score=82.0,
        confirmed=True,
        quality_score=88.0,
        quality_level="FORTE",
        actionable=True,
        decision="EXECUTAR",
        decision_reason="contexto e risco favoráveis",
        market_context="ALTA",
        market_direction="COMPRA",
        market_score=80.0,
        operational_state_available=True,
        trades_today=1,
        consecutive_losses=0,
        symbol="TEST",
        timeframe="5m",
    )


def test_from_path_restores_memory_and_preserves_metadata(tmp_path):
    path = tmp_path / "state" / "operations.json"
    first = PersistentOperationalRecorder.from_path(path)
    timestamp = datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc)

    recorded = first.record_operation(
        snapshot(),
        timestamp=timestamp,
        result="PENDENTE",
        entry_conditions=("fechamento confirmado", "pressão compradora"),
    )
    first.settle_operation(recorded.memory, "WIN")

    restored = PersistentOperationalRecorder.from_path(path)
    records = restored.memory.records()

    assert len(records) == 1
    assert records[0].timestamp == timestamp
    assert records[0].signal is Signal.COMPRA
    assert records[0].result == "WIN"
    assert records[0].symbol == "TEST"
    assert records[0].timeframe == "5m"
    assert records[0].quality_score == 88.0
    assert records[0].quality_level == "FORTE"
    assert records[0].entry_conditions == ("fechamento confirmado", "pressão compradora")


def test_persistence_is_updated_after_each_operation_change(tmp_path):
    path = tmp_path / "operations.json"
    recorder = PersistentOperationalRecorder.from_path(path)
    timestamp = datetime(2026, 9, 9, 1, 1, tzinfo=timezone.utc)

    recorded = recorder.record_operation(snapshot(), timestamp=timestamp)
    assert path.exists()
    assert OperationMemoryStore(path).load().records() == (recorded.memory,)

    updated = recorder.settle_operation(recorded.memory, "LOSS")
    assert OperationMemoryStore(path).load().records() == (updated,)


def test_invalid_persisted_state_fails_closed(tmp_path):
    path = tmp_path / "operations.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="arquivo de memória inválido"):
        PersistentOperationalRecorder.from_path(path)


def test_invalid_store_dependency_is_rejected():
    with pytest.raises(TypeError, match="store deve ser OperationMemoryStore"):
        PersistentOperationalRecorder(store=object())
