from datetime import datetime, timedelta

import pytest

from core.decision_audit import AuditValidationError, DecisionAudit, DecisionAuditRecord
from core.decision_snapshot import DecisionSnapshot
from core.kill_switch import KillSwitch, KillSwitchValidationError
from core.models import Signal
from core.operation_memory import MemoryValidationError, OperationMemory, OperationMemoryRecord


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
        market_direction="ALTA",
        market_score=0.9,
        operational_state_available=True,
        trades_today=1,
        consecutive_losses=0,
        symbol="TEST",
        timeframe="5m",
    )


def record(ts: datetime, result: str = "PENDENTE", signal: Signal = Signal.COMPRA) -> OperationMemoryRecord:
    return OperationMemoryRecord(
        timestamp=ts,
        signal=signal,
        score=8.0,
        decision="EXECUTAR",
        reason="teste",
        result=result,
        symbol="TEST",
        timeframe="5m",
        quality_score=80.0,
        quality_level="FORTE",
        entry_conditions=("confirmação", "contexto favorável"),
    )


def test_audit_is_immutable_and_chronological():
    audit = DecisionAudit()
    first = DecisionAuditRecord(datetime(2026, 1, 1), snapshot())
    second = DecisionAuditRecord(datetime(2026, 1, 2), snapshot("AGUARDAR", "AGUARDAR"))
    audit.append(first)
    audit.append(second)
    assert audit.summary() == {
        "total": 2,
        "executar": 1,
        "bloquear": 0,
        "aguardar": 1,
        "compra": 1,
        "venda": 0,
    }
    with pytest.raises(AuditValidationError):
        audit.append(DecisionAuditRecord(datetime(2025, 12, 31), snapshot()))


def test_audit_serializes_timestamp_and_snapshot():
    item = DecisionAuditRecord(datetime(2026, 1, 1, 12, 0), snapshot())
    data = item.as_dict()
    assert data["timestamp"] == "2026-01-01T12:00:00"
    assert data["signal"] == "COMPRA"
    assert data["decision"] == "EXECUTAR"


def test_memory_rejects_out_of_order_records_and_reports_metrics():
    memory = OperationMemory()
    start = datetime(2026, 1, 1)
    memory.append(record(start, "WIN"))
    memory.append(record(start + timedelta(minutes=1), "LOSS", Signal.VENDA))
    memory.append(record(start + timedelta(minutes=2), "PENDENTE"))
    metrics = memory.metrics()
    assert metrics["completed"] == 2
    assert metrics["wins"] == 1
    assert metrics["losses"] == 1
    assert metrics["win_rate"] == 0.5
    assert metrics["loss_streak"] == 1
    assert metrics["max_loss_streak"] == 1
    assert metrics["direction"]["COMPRA"]["wins"] == 1
    assert metrics["direction"]["VENDA"]["losses"] == 1
    with pytest.raises(MemoryValidationError):
        memory.append(record(start - timedelta(seconds=1)))


def test_memory_rejects_invalid_entry_conditions():
    with pytest.raises(MemoryValidationError):
        OperationMemoryRecord(
            timestamp=datetime(2026, 1, 1),
            signal=Signal.COMPRA,
            score=8,
            decision="EXECUTAR",
            reason="teste",
            entry_conditions=("",),
        )


def test_kill_switch_is_fail_safe_and_independent():
    switch = KillSwitch()
    assert switch.allows_execution() is True
    state = switch.activate("limite de perda atingido")
    assert state.enabled is True
    assert switch.allows_execution() is False
    with pytest.raises(RuntimeError, match="limite de perda atingido"):
        switch.guard()
    switch.deactivate()
    assert switch.state.enabled is False
    assert switch.state.reason is None


def test_kill_switch_requires_reason_when_active():
    with pytest.raises(KillSwitchValidationError):
        KillSwitch().activate("")
