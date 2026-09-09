from datetime import datetime, timezone

from core.decision_snapshot import DecisionSnapshot
from core.kill_switch import KillSwitch
from core.models import Signal
from core.p4_operational_recorder import P4OperationalRecorder
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def make_snapshot() -> DecisionSnapshot:
    return DecisionSnapshot(
        signal=Signal.COMPRA.value,
        analysis_score=80.0,
        confirmed=True,
        quality_score=60.0,
        quality_level="MODERADA",
        actionable=True,
        decision="EXECUTAR",
        decision_reason="contexto favorável",
        market_context="FAVORAVEL",
        market_direction="ALTA",
        market_score=80.0,
        operational_state_available=True,
        trades_today=1,
        consecutive_losses=0,
        symbol="BTCUSD",
        timeframe="5m",
    )


def make_request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def test_gateway_audits_before_memory_and_reuses_same_audit_event():
    recorder = P4OperationalRecorder()
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), recorder)
    timestamp = datetime(2026, 9, 8, tzinfo=timezone.utc)

    result = gateway.execute(
        "req-audit-1",
        make_request(),
        snapshot=make_snapshot(),
        timestamp=timestamp,
        entry_conditions=("candle_confirmado", "contexto_favoravel"),
    )

    assert result.status is GatewayStatus.ACCEPTED
    assert result.recorded_operation is not None
    assert len(recorder.audit.records()) == 1
    assert len(recorder.memory.records()) == 1
    assert result.recorded_operation.audit.snapshot == make_snapshot()
    assert result.recorded_operation.memory.result == "PENDENTE"
    assert result.recorded_operation.memory.entry_conditions == (
        "candle_confirmado",
        "contexto_favoravel",
    )


def test_blocked_execution_is_audited_but_not_written_to_operation_memory():
    recorder = P4OperationalRecorder()
    kill_switch = KillSwitch()
    kill_switch.activate("emergência")
    gateway = ExecutionGateway(PaperExecutor(), kill_switch, recorder)

    result = gateway.execute(
        "req-blocked-1",
        make_request(),
        snapshot=make_snapshot(),
    )

    assert result.status is GatewayStatus.BLOCKED
    assert len(recorder.audit.records()) == 1
    assert len(recorder.memory.records()) == 0


def test_invalid_request_is_not_audit_event():
    recorder = P4OperationalRecorder()
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), recorder)
    invalid = ExecutionRequest(
        symbol="BTCUSD",
        signal=Signal.AGUARDAR,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )

    result = gateway.execute("req-invalid-1", invalid, snapshot=make_snapshot())

    assert result.status is GatewayStatus.INVALID_REQUEST
    assert len(recorder.audit.records()) == 0
    assert len(recorder.memory.records()) == 0
