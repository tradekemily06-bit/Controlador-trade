from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from datetime import datetime

import pytest

from core.runtime_checkpoint import RuntimeCheckpointStore
from core.trading_runtime import TradingRuntime
from data.feed import MarketDataRequest
from execution.gateway import GatewayResult, GatewayStatus
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from core.p41_controlled_automation import AutomationPolicy
from core.demo_readiness import DemoReadinessReport
from core.p40_risk_budget import BudgetDecision, RiskBudgetAssessment


@dataclass
class FakeOrchestration:
    executable: bool


class FakeOrchestrator:
    def __init__(self, executable: bool = False) -> None:
        self.executable = executable
        self.calls = 0

    def evaluate(self, request, **kwargs):
        self.calls += 1
        return FakeOrchestration(self.executable)


class FakeCoordinator:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.build_calls = []
        self.execute_calls = []

    def build_plan(self, orchestration, **kwargs):
        self.build_calls.append((orchestration, kwargs))
        return SimpleNamespace(request_id=kwargs["request_id"])

    def execute_plan(self, plan, **kwargs):
        self.execute_calls.append((plan, kwargs))
        status = GatewayStatus.ACCEPTED if self.accepted else GatewayStatus.BLOCKED
        return GatewayResult(status, "ok" if self.accepted else "bloqueado")


def request() -> MarketDataRequest:
    return MarketDataRequest(symbol="TEST", timeframe="5m", limit=3)


def test_runtime_requires_dependencies() -> None:
    with pytest.raises(ValueError, match="orchestrator"):
        TradingRuntime(orchestrator=None, coordinator=FakeCoordinator())
    with pytest.raises(ValueError, match="coordinator"):
        TradingRuntime(orchestrator=FakeOrchestrator(), coordinator=None)


def test_runtime_rejects_invalid_cycle_limit() -> None:
    runtime = TradingRuntime(orchestrator=FakeOrchestrator(), coordinator=FakeCoordinator())
    with pytest.raises(ValueError, match="max_cycles"):
        runtime.run(request(), operational_state=None, market_context=None, amount=1, duration_seconds=60, max_cycles=0)


def test_runtime_does_not_execute_non_executable_decision() -> None:
    orchestrator = FakeOrchestrator(executable=False)
    coordinator = FakeCoordinator()
    result = TradingRuntime(orchestrator=orchestrator, coordinator=coordinator).run(
        request(), operational_state=None, market_context=None, amount=1, duration_seconds=60, max_cycles=3
    )
    assert len(result.cycles) == 3
    assert result.executed_cycles == 0
    assert coordinator.build_calls == []
    assert coordinator.execute_calls == []
    assert not result.stopped


def test_runtime_stops_after_rejected_execution() -> None:
    orchestrator = FakeOrchestrator(executable=True)
    coordinator = FakeCoordinator(accepted=False)
    result = TradingRuntime(orchestrator=orchestrator, coordinator=coordinator).run(
        request(), operational_state=None, market_context=None, amount=1, duration_seconds=60, max_cycles=5
    )
    assert len(result.cycles) == 1
    assert result.stopped
    assert result.stop_reason == "bloqueado"
    assert result.executed_cycles == 0


def test_runtime_uses_deterministic_request_ids() -> None:
    coordinator = FakeCoordinator(accepted=True)
    result = TradingRuntime(orchestrator=FakeOrchestrator(executable=True), coordinator=coordinator).run(
        request(), operational_state=None, market_context=None, amount=1, duration_seconds=60, max_cycles=2
    )
    assert [call[1]["request_id"] for call in coordinator.build_calls] == ["runtime-000001", "runtime-000002"]
    assert result.executed_cycles == 2
    assert not result.stopped


def test_runtime_persists_last_safe_cycle(tmp_path) -> None:
    store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    result = TradingRuntime(orchestrator=FakeOrchestrator(executable=False), coordinator=FakeCoordinator()).run(
        request(), operational_state=None, market_context=None, amount=1, duration_seconds=60,
        max_cycles=3, checkpoint_store=store, session_id="session-1",
    )
    checkpoint = store.load()
    assert len(result.cycles) == 3
    assert checkpoint.session_id == "session-1"
    assert checkpoint.last_cycle == 3
    assert checkpoint.last_request_id is None
    assert isinstance(checkpoint.updated_at, datetime)


def test_runtime_checkpoint_records_execution_request_id(tmp_path) -> None:
    store = RuntimeCheckpointStore(tmp_path / "checkpoint.json")
    TradingRuntime(orchestrator=FakeOrchestrator(executable=True), coordinator=FakeCoordinator()).run(
        request(), operational_state=None, market_context=None, amount=1, duration_seconds=60,
        max_cycles=1, checkpoint_store=store, session_id="session-2",
    )
    assert store.load().last_request_id == "runtime-000001"


def test_checkpoint_requires_session_id(tmp_path) -> None:
    with pytest.raises(ValueError, match="session_id"):
        TradingRuntime(orchestrator=FakeOrchestrator(), coordinator=FakeCoordinator()).run(
            request(), operational_state=None, market_context=None, amount=1, duration_seconds=60,
            checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        )


class FakeOrderQuery:
    def __init__(self, status):
        self.status = status

    def query_order(self, external_id):
        return ExternalOrderObservation(external_id, self.status, "observed")


def test_runtime_reconciles_executed_order_without_inventing_financial_outcome():
    snapshot = TradingRuntime.reconcile_external_cycle(
        cycle_id="runtime-000001",
        external_id="123",
        query_port=FakeOrderQuery(ExternalOrderStatus.EXECUTED),
    )
    assert snapshot is not None
    assert snapshot.terminal_state == "COMPLETED"
    assert snapshot.outcome == "UNKNOWN"
    assert snapshot.financial_result is None
    assert snapshot.reconciliation_state.value == "UNVERIFIED"


def test_runtime_reconciles_not_executed_order_as_blocked_without_financial_inference():
    snapshot = TradingRuntime.reconcile_external_cycle(
        cycle_id="runtime-000002",
        external_id="456",
        query_port=FakeOrderQuery(ExternalOrderStatus.NOT_EXECUTED),
    )
    assert snapshot is not None
    assert snapshot.terminal_state == "BLOCKED"
    assert snapshot.outcome == "UNKNOWN"
    assert snapshot.financial_result is None
    assert snapshot.reconciliation_state.value == "UNVERIFIED"


def test_runtime_keeps_pending_external_order_open():
    snapshot = TradingRuntime.reconcile_external_cycle(
        cycle_id="runtime-000003",
        external_id="789",
        query_port=FakeOrderQuery(ExternalOrderStatus.PENDING),
    )
    assert snapshot is None



def test_runtime_reuses_senior_cycle_id_for_automation_handoff():
    from core.p46_automation_lifecycle import AutomationLifecycleState
    from core.senior_context_cycle import SeniorContextQuality
    from core.senior_risk_reasoning import RiskKnowledgeStatus

    class FakeSeniorContext:
        cycle_id = "senior-cycle-001"
        quality = SeniorContextQuality.COMPLETE
        execution_authorized = False
        class Risk:
            execution_authorized = False
            status = RiskKnowledgeStatus.ASSESSED
        risk_assessment = Risk()

    class ExecutableOrchestrator(FakeOrchestrator):
        def evaluate(self, request, **kwargs):
            self.calls += 1
            return SimpleNamespace(
                executable=True,
                senior_context=FakeSeniorContext(),
            )

    class LineageCoordinator(FakeCoordinator):
        def build_plan(self, orchestration, **kwargs):
            self.build_calls.append((orchestration, kwargs))
            return SimpleNamespace(request_id=kwargs["request_id"])

        def build_intent(self, plan, *, orchestration):
            from datetime import datetime, timezone
            from core.execution_intent import ExecutionIntent
            from core.models import Signal
            from execution.ports import ExecutionMode
            return ExecutionIntent(
                request_id=plan.request_id,
                symbol="TEST",
                signal=Signal.COMPRA,
                amount=0.01,
                duration_seconds=60,
                mode=ExecutionMode.DEMO,
                created_at=datetime.now(timezone.utc),
                cycle_id=orchestration.senior_context.cycle_id,
            )

        def execute_plan(self, plan, **kwargs):
            self.execute_calls.append((plan, kwargs))
            assert kwargs["orchestration"].senior_context.cycle_id == "senior-cycle-001"
            return GatewayResult(GatewayStatus.ACCEPTED, "ok")

    result = TradingRuntime(
        orchestrator=ExecutableOrchestrator(executable=True),
        coordinator=LineageCoordinator(),
    ).run(
        request(),
        operational_state=None,
        amount=0.01,
        duration_seconds=60,
        automation_policy=AutomationPolicy(enabled=True, minimum_interval_seconds=0),
        automation_readiness=DemoReadinessReport(True, ()),
        automation_risk_budget=RiskBudgetAssessment(
            BudgetDecision.APPROVED, 0.0, 1, "approved"
        ),
    )
    assert result.cycles[0].automation_lifecycle is not None
    assert result.cycles[0].automation_lifecycle.state is AutomationLifecycleState.DISPATCHED

def test_runtime_integrates_controlled_automation_gates_without_second_executor():
    from core.p46_automation_lifecycle import AutomationLifecycleState

    result = TradingRuntime(
        orchestrator=FakeOrchestrator(executable=False),
        coordinator=FakeCoordinator(),
    ).run(
        request(),
        operational_state=None,
        amount=0.01,
        duration_seconds=60,
        automation_policy=AutomationPolicy(enabled=True, minimum_interval_seconds=0),
        automation_readiness=DemoReadinessReport(True, ()),
        automation_risk_budget=RiskBudgetAssessment(
            BudgetDecision.APPROVED, 0.0, 0, "approved"
        ),
    )
    cycle = result.cycles[0]
    assert cycle.automation_lifecycle is not None
    assert cycle.automation_lifecycle.state is AutomationLifecycleState.BLOCKED
    assert cycle.execution is None
