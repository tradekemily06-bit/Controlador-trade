from __future__ import annotations

import multiprocessing
from pathlib import Path

from core.decision_snapshot import DecisionSnapshot
from core.models import Signal
from core.operational_state import OperationalState
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport
from core.p117_real_admission import RealAdmissionBoundary
from core.risk_state_fingerprint import risk_state_identity
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class CountingAdapter:
    def __init__(self, calls):
        self.calls = calls

    def is_available(self):
        return True

    def execute(self, request):
        with self.calls.get_lock():
            self.calls.value += 1
        return ExecutionResult(True, "accepted", "external-recovery-matrix")


class RiskProvider:
    def current_risk_state(self):
        return OperationalState(
            balance=1000.0, equity=1000.0, realized_pnl=0.0,
            unrealized_pnl=0.0, trades_today=0, consecutive_losses=0,
            open_positions=0, net_position=0.0, exposure=0.0, market_open=True,
        )


class SafetyProvider:
    def current_real_safety(self):
        return RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True,
            market_healthy=True, recovery_safe=True,
            risk_approved=True, broker_available=True,
        )


def _state() -> OperationalState:
    return RiskProvider().current_risk_state()


def _snapshot() -> DecisionSnapshot:
    state = _state()
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None, operational_state_available=True,
        trades_today=state.trades_today, consecutive_losses=state.consecutive_losses,
        symbol="TEST", timeframe="5m", risk_state_identity=risk_state_identity(state),
    )


def _authorization() -> RealExecutionAuthorization:
    return RealExecutionAuthorization("auth", "audit", "fake", "fake-adapter", True, True)


def _admission():
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True, broker_available=True,
        broker_id="fake",
    )


def _safety() -> RealSafetyReport:
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True,
        risk_approved=True, broker_available=True,
    )


def _request(request_id: str) -> ExecutionRequest:
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id)


def _gateway(path: Path, calls) -> RealExecutionGateway:
    registry = BrokerRegistry()
    registry.register("fake", CountingAdapter(calls))
    return RealExecutionGateway(
        BrokerAdapterGateway(registry), ExecutionLedger(path),
        RiskProvider(), SafetyProvider(),
    )


def _dispatch(path: str, request_id: str, calls, queue) -> None:
    result = _gateway(Path(path), calls).execute(
        broker="fake", request_id=request_id, request=_request(request_id),
        authorization=_authorization(), admission=_admission(),
        safety=_safety(), snapshot=_snapshot(),
    )
    queue.put(result.status)


def _reconcile(path: str, request_id: str, queue) -> None:
    calls = multiprocessing.Value("i", 0)
    _gateway(Path(path), calls).reconcile_unknown(request_id, executed=False)
    queue.put("RECONCILED")


def test_reserved_dispatch_and_reconciliation_race_never_sends(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ExecutionLedger(path).reserve("reserved-race")
    calls = multiprocessing.Value("i", 0)
    queue = multiprocessing.Queue()
    ctx = multiprocessing.get_context("fork")
    processes = [
        ctx.Process(target=_dispatch, args=(str(path), "reserved-race", calls, queue)),
        ctx.Process(target=_reconcile, args=(str(path), "reserved-race", queue)),
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0

    statuses = {queue.get(timeout=2), queue.get(timeout=2)}
    assert calls.value == 0
    assert "RECONCILED" in statuses
    assert RealGatewayStatus.UNKNOWN in statuses or RealGatewayStatus.BLOCKED in statuses
    assert ExecutionLedger(path).status("reserved-race") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED


def test_accepted_request_remains_terminal_across_restart_and_cannot_send_again(tmp_path: Path):
    path = tmp_path / "ledger.json"
    calls = multiprocessing.Value("i", 0)
    first = _gateway(path, calls)
    first_result = first.execute(
        broker="fake", request_id="terminal-restart", request=_request("terminal-restart"),
        authorization=_authorization(), admission=_admission(), safety=_safety(), snapshot=_snapshot(),
    )
    assert first_result.status is RealGatewayStatus.ADMITTED
    assert calls.value == 1

    restored_calls = multiprocessing.Value("i", 0)
    restored = _gateway(path, restored_calls)
    second_result = restored.execute(
        broker="fake", request_id="terminal-restart", request=_request("terminal-restart"),
        authorization=_authorization(), admission=_admission(), safety=_safety(), snapshot=_snapshot(),
    )
    assert second_result.status is RealGatewayStatus.BLOCKED
    assert restored_calls.value == 0
    assert ExecutionLedger(path).status("terminal-restart") is ExecutionLedgerStatus.ACCEPTED


def test_reconciled_executed_state_is_terminal_and_never_resubmits(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("reconciled-executed")
    ledger.mark_unknown("reconciled-executed")
    calls = multiprocessing.Value("i", 0)
    gateway = _gateway(path, calls)
    gateway.reconcile_unknown("reconciled-executed", executed=True)

    restored_calls = multiprocessing.Value("i", 0)
    restored = _gateway(path, restored_calls)
    result = restored.execute(
        broker="fake", request_id="reconciled-executed", request=_request("reconciled-executed"),
        authorization=_authorization(), admission=_admission(), safety=_safety(), snapshot=_snapshot(),
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert restored_calls.value == 0
    assert ExecutionLedger(path).status("reconciled-executed") is ExecutionLedgerStatus.RECONCILED_EXECUTED
