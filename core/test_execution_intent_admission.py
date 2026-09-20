from datetime import datetime, timezone

import pytest

from core.execution_intent import ExecutionIntent
from core.execution_intent_admission import ExecutionIntentAdmission
from core.models import Signal
from core.kill_switch import KillSwitch
from core.senior_context_cycle import SeniorContextCycle, SeniorContextQuality
from core.senior_risk_reasoning import RiskKnowledgeStatus, SeniorRiskAssessment
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionResult


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


def make_senior_context(quality=SeniorContextQuality.COMPLETE):
    risk = SeniorRiskAssessment(
        status=RiskKnowledgeStatus.ASSESSED,
        observations=(),
        material_risks=(),
        unknowns=(),
        questions=(),
        reassessment_triggers=(),
        execution_authorized=False,
    )
    return SeniorContextCycle(
        cycle_id="admission-test",
        whole_graph=None,
        temporal_context=None,
        market_reading=None,
        senior_assessment=None,
        risk_assessment=risk,
        validated_knowledge_ids=(),
        unresolved_questions=(),
        quality=quality,
        execution_authorized=False,
    )


def test_admission_preserves_contract_and_uses_gateway():
    executor = RecordingExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), allow_ephemeral=True)
    result = ExecutionIntentAdmission(gateway).admit(make_intent(), senior_context=make_senior_context())
    assert result.status is GatewayStatus.ACCEPTED
    assert executor.calls == 1


def test_same_intent_is_not_executed_twice():
    executor = RecordingExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), allow_ephemeral=True)
    admission = ExecutionIntentAdmission(gateway)
    intent = make_intent()
    context = make_senior_context()
    first = admission.admit(intent, senior_context=context)
    second = admission.admit(intent, senior_context=context)
    assert first.status is GatewayStatus.ACCEPTED
    assert second.status is GatewayStatus.DUPLICATE
    assert executor.calls == 1


def test_invalid_input_fails_closed_before_gateway():
    executor = RecordingExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), allow_ephemeral=True)
    with pytest.raises(ValueError, match="intent"):
        ExecutionIntentAdmission(gateway).admit(object(), senior_context=make_senior_context())
    assert executor.calls == 0


def test_missing_senior_context_fails_closed_before_gateway():
    executor = RecordingExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), allow_ephemeral=True)
    with pytest.raises(ValueError, match="contexto sênior obrigatório"):
        ExecutionIntentAdmission(gateway).admit(make_intent())
    assert executor.calls == 0


def test_incomplete_senior_context_fails_closed_before_gateway():
    executor = RecordingExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), allow_ephemeral=True)
    with pytest.raises(ValueError, match="contexto sênior incompleto"):
        ExecutionIntentAdmission(gateway).admit(
            make_intent(),
            senior_context=make_senior_context(SeniorContextQuality.REASSESS),
        )
    assert executor.calls == 0


def test_kill_switch_blocks_before_executor():
    executor = RecordingExecutor()
    switch = KillSwitch()
    switch.activate("P27 test")
    gateway = ExecutionGateway(executor, switch, allow_ephemeral=True)
    result = ExecutionIntentAdmission(gateway).admit(make_intent(), senior_context=make_senior_context())
    assert result.status is GatewayStatus.BLOCKED
    assert executor.calls == 0
