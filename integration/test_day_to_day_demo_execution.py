from __future__ import annotations

from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from core.operational_state import OperationalState
from core.operational_runtime import build_operational_runtime
from core.risk_manager import RiskManager
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class FakeDemoExecutor:
    def __init__(self):
        self.requests = []

    def is_available(self):
        return True

    def execute(self, request):
        self.requests.append(request)
        return ExecutionResult(True, "DEMO accepted", "ext-demo-1")

    def read_operational_state(self):
        return OperationalState(
            realized_pnl=0.0,
            trades_today=len(self.requests),
            consecutive_losses=0,
        )


def test_execute_demo_routes_explicit_action_through_shared_gateway(tmp_path: Path):
    from integration.ecosystem_service import EcosystemService

    executor = FakeDemoExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    service = EcosystemService(operational_runtime=runtime)

    decision = service.analyze({"score": 88, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})
    result = service.execute_demo(
        symbol="EURUSD",
        signal="COMPRA",
        amount=0.01,
        duration_seconds=60,
        request_id="ui-demo-1",
        decision_id=decision.decision_id,
    )

    assert result["accepted"] is True
    assert result["mode"] == "DEMO"
    assert result["real"] is False
    assert result["external_id"] == "ext-demo-1"
    assert len(executor.requests) == 1
    assert executor.requests[0].mode is ExecutionMode.DEMO
    assert executor.requests[0].signal is Signal.COMPRA
    journal = runtime.daily_journal.entries()
    assert len(journal) == 1
    assert journal[0].request_id == "ui-demo-1"
    assert journal[0].external_id == "ext-demo-1"


def test_execute_demo_rejects_aguardar(tmp_path: Path):
    from integration.ecosystem_service import EcosystemService

    runtime = build_operational_runtime(tmp_path, executor=FakeDemoExecutor())
    service = EcosystemService(operational_runtime=runtime)

    try:
        service.execute_demo(
            symbol="EURUSD",
            signal="AGUARDAR",
            amount=0.01,
            duration_seconds=60,
        )
    except ValueError as exc:
        assert "AGUARDAR" in str(exc)
    else:
        raise AssertionError("AGUARDAR should never reach the gateway")


def test_gateway_duplicate_request_stays_blocked(tmp_path: Path):
    from integration.ecosystem_service import EcosystemService

    executor = FakeDemoExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    service = EcosystemService(operational_runtime=runtime)

    decision = service.analyze({"score": 88, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})
    first = service.execute_demo(
        symbol="EURUSD",
        signal="COMPRA",
        amount=0.01,
        duration_seconds=60,
        request_id="duplicate-demo",
        decision_id=decision.decision_id,
    )
    second = service.execute_demo(
        symbol="EURUSD",
        signal="COMPRA",
        amount=0.01,
        duration_seconds=60,
        request_id="duplicate-demo",
        decision_id=decision.decision_id,
    )

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["status"] == "DUPLICATE"
    assert len(executor.requests) == 1
    assert len(runtime.daily_journal.entries()) == 2
    assert runtime.daily_journal.entries()[0].status == "DUPLICATE"


def test_execute_demo_respects_configured_risk_gate(tmp_path: Path):
    from integration.ecosystem_service import EcosystemService

    executor = FakeDemoExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    service = EcosystemService(operational_runtime=runtime)
    decision = service.analyze({"score": 88, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m"})
    first = service.execute_demo(
        symbol="EURUSD",
        signal="COMPRA",
        amount=0.01,
        duration_seconds=60,
        request_id="risk-seed",
        decision_id=decision.decision_id,
    )
    assert first["accepted"] is True
    service.risk = RiskManager(max_operations=1)

    result = service.execute_demo(
        symbol="EURUSD",
        signal="COMPRA",
        amount=0.01,
        duration_seconds=60,
        request_id="risk-blocked",
    )

    assert result["accepted"] is False
    assert result["status"] == "RISK_BLOCKED"
    assert executor.requests == []


def test_execute_demo_automatically_links_latest_decision_context(tmp_path: Path):
    from integration.ecosystem_service import EcosystemService

    executor = FakeDemoExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    service = EcosystemService(operational_runtime=runtime)
    decision = service.analyze({
        "score": 88,
        "confirmed": True,
        "filters_ok": True,
        "symbol": "EURUSD",
        "timeframe": "5m",
    })

    result = service.execute_demo(
        symbol="EURUSD",
        signal=decision.signal.value,
        amount=0.01,
        duration_seconds=60,
        decision_id=decision.decision_id,
    )

    assert result["accepted"] is True
    journal = runtime.daily_journal.entries()[0]
    assert journal.decision_id == decision.decision_id
    assert journal.timeframe == "5m"
    assert journal.score == 88


def test_execute_demo_requires_registered_confirmed_decision(tmp_path: Path):
    from integration.ecosystem_service import EcosystemService

    executor = FakeDemoExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    service = EcosystemService(operational_runtime=runtime)

    try:
        service.execute_demo(
            symbol="EURUSD",
            signal="COMPRA",
            amount=0.01,
            duration_seconds=60,
        )
    except ValueError as exc:
        assert "decision_id" in str(exc)
    else:
        raise AssertionError("execution without a decision must be blocked")
