from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from datetime import datetime

import pytest

from core.runtime_checkpoint import RuntimeCheckpointStore
from core.trading_runtime import TradingRuntime
from data.feed import MarketDataRequest
from execution.gateway import GatewayResult, GatewayStatus
from execution.ports import ExecutionMode
from execution.real_gateway import RealGatewayResult, RealGatewayStatus


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


class FakeRealCoordinator:
    def __init__(self) -> None:
        self.calls = []

    def execute_plan(self, plan, **kwargs):
        self.calls.append((plan, kwargs))
        return RealGatewayResult(RealGatewayStatus.ADMITTED, "real-ok")


def test_runtime_requires_explicit_real_session_when_real_is_selected():
    runtime = TradingRuntime(orchestrator=FakeOrchestrator(executable=True), coordinator=FakeCoordinator())
    with pytest.raises(ValueError, match="sessão REAL"):
        runtime.run(
            request(), operational_state=None, market_context=None, amount=1,
            duration_seconds=60, mode=ExecutionMode.REAL, explicit_real_approval=True,
        )


def test_runtime_real_selection_requires_explicit_approval():
    real = FakeRealCoordinator()
    runtime = TradingRuntime(
        orchestrator=FakeOrchestrator(executable=True),
        coordinator=FakeCoordinator(),
        real_coordinator=real,
    )
    with pytest.raises(ValueError, match="aprovação explícita"):
        runtime.run(
            request(), operational_state=None, market_context=None, amount=1,
            duration_seconds=60, mode=ExecutionMode.REAL,
        )


def test_runtime_routes_selected_real_mode_only_to_real_coordinator():
    real = FakeRealCoordinator()
    runtime = TradingRuntime(
        orchestrator=FakeOrchestrator(executable=True),
        coordinator=FakeCoordinator(),
        real_coordinator=real,
    )
    result = runtime.run(
        request(), operational_state=None, market_context=None, amount=1,
        duration_seconds=60, max_cycles=1, mode=ExecutionMode.REAL,
        explicit_real_approval=True,
    )
    assert result.executed_cycles == 1
    assert len(real.calls) == 1
