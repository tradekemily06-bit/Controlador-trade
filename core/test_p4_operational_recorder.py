from datetime import datetime, timedelta

import pytest

from core.kill_switch import KillSwitch
from core.models import Signal
from core.operation_memory import OperationMemory
from core.p4_operational_recorder import P4OperationalRecorder
from core.decision_snapshot import DecisionSnapshot


def snapshot(decision: str = "EXECUTAR", signal: str = "COMPRA") -> DecisionSnapshot:
    return DecisionSnapshot(
        signal=signal,
        analysis_score=8.0,
        confirmed=True,
        quality_score=80.0,
        quality_level="FORTE",
        actionable=True,
        decision=decision,
        decision_reason="contexto favorável e risco aprovado",
        market_context="FAVORAVEL",
        market_direction="ALTA" if signal == "COMPRA" else "BAIXA",
        market_score=0.9,
        operational_state_available=True,
        trades_today=1,
        consecutive_losses=0,
        symbol="TEST",
        timeframe="5m",
    )


def test_recorder_enforces_audit_before_memory():
    recorder = P4OperationalRecorder()
    ts = datetime(2026, 1, 1, 10, 0)
    recorded = recorder.record_operation(
        snapshot(), timestamp=ts, entry_conditions=("candle confirmado",)
    )
    assert len(recorder.audit.records()) == 1
    assert len(recorder.memory.records()) == 1
    assert recorded.audit.timestamp == recorded.memory.timestamp == ts
    assert recorded.memory.signal is Signal.COMPRA
    assert recorded.memory.result == "PENDENTE"
    assert recorder.audit.records()[0].snapshot == snapshot()


def test_recorder_settles_without_duplicate_memory_record():
    recorder = P4OperationalRecorder()
    recorded = recorder.record_operation(snapshot(), timestamp=datetime(2026, 1, 1))
    settled = recorder.settle_operation(recorded.memory, "WIN")
    assert settled.result == "WIN"
    assert len(recorder.memory.records()) == 1
    assert recorder.memory.records()[0].result == "WIN"
    assert len(recorder.audit.records()) == 1


def test_recorder_rejects_second_settlement():
    recorder = P4OperationalRecorder()
    recorded = recorder.record_operation(snapshot(), timestamp=datetime(2026, 1, 1))
    recorder.settle_operation(recorded.memory, "LOSS")
    with pytest.raises(ValueError, match="somente registros pendentes"):
        recorder.settle_operation(recorded.memory, "WIN")


def test_recorder_kill_switch_is_independent_of_strategy_snapshot():
    switch = KillSwitch()
    recorder = P4OperationalRecorder(kill_switch=switch)
    assert recorder.can_execute() is True
    switch.activate("proteção manual")
    assert recorder.can_execute() is False
    with pytest.raises(RuntimeError, match="proteção manual"):
        recorder.guard_execution()
    # The audit/memory layer can still record what happened; the gate is separate.
    recorder.record_operation(snapshot("BLOQUEAR"), timestamp=datetime(2026, 1, 1))
    assert recorder.audit.summary()["bloquear"] == 1


def test_memory_quality_metrics_are_deterministic():
    memory = OperationMemory()
    base = datetime(2026, 1, 1)
    first = recorder = P4OperationalRecorder(memory=memory).record_operation
    first(snapshot(), timestamp=base, result="WIN")
    first(snapshot(), timestamp=base + timedelta(minutes=1), result="LOSS")
    metrics = memory.metrics()
    assert metrics["quality"]["FORTE"]["total"] == 2
    assert metrics["quality"]["FORTE"]["wins"] == 1
    assert metrics["quality"]["FORTE"]["losses"] == 1
    assert metrics["quality"]["FORTE"]["win_rate"] == 0.5
