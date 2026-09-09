from datetime import datetime, timezone

import pytest

from core.execution_intent import ExecutionIntent
from core.execution_intent_admission import ExecutionIntentAdmission
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionResult
from core.kill_switch import KillSwitch


class RecordingExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "demo accepted", "demo-1")


def make_intent():
    return ExecutionIntent(
        request_id="req-27",
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_admission_preserves_contract_and_uses_gateway():
    executor = RecordingExecutor()
    gateway = ExecutionGateway(executor, KillSwitch())
    result = ExecutionIntentAdmission(gateway).admit(make_intent())
    assert result.status is GatewayStatus.ACCEPTED
    assert executor.calls == 1


def test_same_intent_is_not_executed_twice():
    executor = RecordingExecutor()
    gateway = ExecutionGateway(executor, KillSwitch())
    admission = ExecutionIntentAdmission(gateway)
    intent = make_intent()
    first = admission.admit(intent)
    second = admission.admit(intent)
    assert first.status is GatewayStatus.ACCEPTED
    assert second.status is GatewayStatus.DUPLICATE
    assert executor.calls == 1


def test_invalid_input_fails_closed_before_gateway():
    executor = RecordingExecutor()
    gateway = ExecutionGateway(executor, KillSwitch())
    with pytest.raises(ValueError, match="intent"):
        ExecutionIntentAdmission(gateway).admit(object())
    assert executor.calls == 0


def test_kill_switch_blocks_before_executor():
    executor = RecordingExecutor()
    switch = KillSwitch()
    switch.activate("P27 test")
    gateway = ExecutionGateway(executor, switch)
    result = ExecutionIntentAdmission(gateway).admit(make_intent())
    assert result.status is GatewayStatus.BLOCKED
    assert executor.calls == 0
