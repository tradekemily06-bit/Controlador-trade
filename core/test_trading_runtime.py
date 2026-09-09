from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from core.trading_runtime import TradingRuntime
from data.feed import MarketDataRequest
from execution.gateway import GatewayResult, GatewayStatus


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
    runtime = TradingRuntime(
        orchestrator=FakeOrchestrator(),
        coordinator=FakeCoordinator(),
    )
    with pytest.raises(ValueError, match="max_cycles"):
        runtime.run(
            request(),
            operational_state=None,
            market_context=None,
            amount=1,
            duration_seconds=60,
            max_cycles=0,
        )


def test_runtime_does_not_execute_non_executable_decision() -> None:
    orchestrator = FakeOrchestrator(executable=False)
    coordinator = FakeCoordinator()
    runtime = TradingRuntime(orchestrator=orchestrator, coordinator=coordinator)

    result = runtime.run(
        request(),
        operational_state=None,
        market_context=None,
        amount=1,
        duration_seconds=60,
        max_cycles=3,
    )

    assert len(result.cycles) == 3
    assert result.executed_cycles == 0
    assert coordinator.build_calls == []
    assert coordinator.execute_calls == []
    assert not result.stopped


def test_runtime_stops_after_rejected_execution() -> None:
    orchestrator = FakeOrchestrator(executable=True)
    coordinator = FakeCoordinator(accepted=False)
    runtime = TradingRuntime(orchestrator=orchestrator, coordinator=coordinator)

    result = runtime.run(
        request(),
        operational_state=None,
        market_context=None,
        amount=1,
        duration_seconds=60,
        max_cycles=5,
    )

    assert len(result.cycles) == 1
    assert result.stopped
    assert result.stop_reason == "bloqueado"
    assert result.executed_cycles == 0
    assert len(coordinator.build_calls) == 1
    assert len(coordinator.execute_calls) == 1


def test_runtime_uses_deterministic_request_ids() -> None:
    orchestrator = FakeOrchestrator(executable=True)
    coordinator = FakeCoordinator(accepted=True)
    runtime = TradingRuntime(orchestrator=orchestrator, coordinator=coordinator)

    result = runtime.run(
        request(),
        operational_state=None,
        market_context=None,
        amount=1,
        duration_seconds=60,
        max_cycles=2,
    )

    assert [call[1]["request_id"] for call in coordinator.build_calls] == [
        "runtime-000001",
        "runtime-000002",
    ]
    assert result.executed_cycles == 2
    assert not result.stopped
