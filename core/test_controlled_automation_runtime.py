from __future__ import annotations

from datetime import datetime, timezone

from core.controlled_automation_runtime import ControlledAutomationRuntime
from core.demo_readiness import DemoReadinessReport
from core.execution_intent import ExecutionIntent
from core.models import Signal
from core.p40_risk_budget import BudgetDecision, RiskBudgetAssessment
from core.p41_controlled_automation import AutomationPolicy
from execution.ports import ExecutionMode


def intent():
    return ExecutionIntent(
        request_id="req-auto-1",
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=1.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        created_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        decision_id="decision-1",
        cycle_id="cycle-1",
    )


def readiness():
    return DemoReadinessReport(True, ())


def budget():
    return RiskBudgetAssessment(BudgetDecision.APPROVED, 0.0, 1, "ok")


def test_controlled_automation_chains_p41_to_p44_and_dispatch_state():
    runtime = ControlledAutomationRuntime(
        policy=AutomationPolicy(
            enabled=True, minimum_interval_seconds=0
        )
    )
    result = runtime.prepare(
        cycle_id="cycle-1",
        requested_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        readiness=readiness(),
        risk_budget=budget(),
        intent=intent(),
    )
    assert result.decision.allowed
    assert result.cycle.authorized
    assert result.admission.admitted
    assert result.handoff.handed_off
    assert result.lifecycle.state.value == "DISPATCHED"


def test_blocked_admission_never_reaches_dispatch():
    runtime = ControlledAutomationRuntime(
        policy=AutomationPolicy(
            enabled=True, minimum_interval_seconds=0
        )
    )
    result = runtime.prepare(
        cycle_id="cycle-2",
        requested_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        readiness=DemoReadinessReport(False, ("market data stale",)),
        risk_budget=budget(),
        intent=intent(),
    )
    assert not result.admission.admitted
    assert result.lifecycle.state.value == "BLOCKED"
    assert not result.handoff.handed_off


def test_complete_maps_gateway_acceptance_to_terminal_lifecycle():
    runtime = ControlledAutomationRuntime(
        policy=__import__("core.p41_controlled_automation", fromlist=["AutomationPolicy"]).AutomationPolicy(
            enabled=True, minimum_interval_seconds=0
        )
    )
    prepared = runtime.prepare(
        cycle_id="cycle-1",
        requested_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        readiness=readiness(),
        risk_budget=budget(),
        intent=intent(),
    )

    class Result:
        accepted = True

    result = runtime.complete(prepared, Result())
    assert result.lifecycle.state.value == "COMPLETED"


def test_cycle_mismatch_is_blocked_at_handoff():
    runtime = ControlledAutomationRuntime(policy=AutomationPolicy(enabled=True, minimum_interval_seconds=0))
    mismatched = intent()
    mismatched = ExecutionIntent(
        request_id=mismatched.request_id, symbol=mismatched.symbol, signal=mismatched.signal,
        amount=mismatched.amount, duration_seconds=mismatched.duration_seconds,
        mode=mismatched.mode, created_at=mismatched.created_at,
        decision_id=mismatched.decision_id, cycle_id="different-cycle",
    )
    result = runtime.prepare(
        cycle_id="cycle-4", requested_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        readiness=readiness(), risk_budget=budget(), intent=mismatched,
    )
    assert not result.handoff.handed_off
    assert result.lifecycle.state.value == "BLOCKED"
