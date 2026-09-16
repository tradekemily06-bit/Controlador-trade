from __future__ import annotations

from datetime import datetime, timezone

import json
import multiprocessing
import os
from pathlib import Path

from core.decision_snapshot import DecisionSnapshot
from core.test_p111_p119_real_release import _authorization as _trusted_authorization, _admission as _trusted_admission
from core.models import Signal
from core.operational_state import OperationalState
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport
from core.p117_real_admission import RealAdmissionBoundary
from core.risk_state_fingerprint import risk_state_identity
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus
from execution.adapter_gateway import BrokerAdapterGateway


class CountingAdapter:
    def __init__(self, calls):
        self.calls = calls

    def is_available(self):
        return True

    def execute(self, request):
        with self.calls.get_lock():
            self.calls.value += 1
        return ExecutionResult(True, "accepted", "external-concurrency")


class CrashAfterAcceptanceAdapter:
    def __init__(self, marker: str):
        self.marker = marker

    def is_available(self):
        return True

    def execute(self, request):
        path = Path(self.marker)
        path.write_text(json.dumps({"request_id": request.request_id, "accepted": True}), encoding="utf-8")
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
        os._exit(0)


class RiskProvider:
    def current_risk_state(self):
        return _risk_state()


class SafetyProvider:
    def __init__(self, report: RealSafetyReport):
        self.report = report

    def current_real_safety(self):
        return self.report


def _risk_state() -> OperationalState:
    return OperationalState(
        balance=1000.0,
        equity=1000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        trades_today=0,
        consecutive_losses=0,
        open_positions=0,
        net_position=0.0,
        exposure=0.0,
        market_open=True,
    )


def _safety() -> RealSafetyReport:
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True,
        risk_approved=True, broker_available=True,
    )


def _snapshot() -> DecisionSnapshot:
    state = _risk_state()
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None, operational_state_available=True,
        trades_today=state.trades_today, consecutive_losses=state.consecutive_losses,
        symbol="TEST", timeframe="5m", risk_state_identity=risk_state_identity(state),
        created_at=datetime.now(timezone.utc),
    )


def _authorization(request_id="req-1"):
    return _trusted_authorization(request_id)


def _admission(request_id="req-1", auth=None):
    return _trusted_admission(request_id, auth=auth)


def _request(request_id: str) -> ExecutionRequest:
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id)


def _gateway(path: Path, adapter) -> RealExecutionGateway:
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(path),
        RiskProvider(),
        SafetyProvider(_safety()),
    )


def _dispatch_worker(path: str, request_id: str, calls, queue) -> None:
    gateway = _gateway(Path(path), CountingAdapter(calls))
    result = gateway.execute(
        broker="fake", request_id=request_id, request=_request(request_id),
        authorization=_authorization(), admission=_admission(),
        safety=_safety(), snapshot=_snapshot(),
    )
    queue.put(result.status)


def _reconcile_worker(path: str, request_id: str, queue) -> None:
    gateway = _gateway(Path(path), CountingAdapter(multiprocessing.Value("i", 0)))
    gateway.reconcile_unknown(request_id, executed=False)
    queue.put("RECONCILED")


def _crash_worker(path: str, marker: str, request_id: str) -> None:
    gateway = _gateway(Path(path), CrashAfterAcceptanceAdapter(marker))
    gateway.execute(
        broker="fake", request_id=request_id, request=_request(request_id),
        authorization=_authorization(), admission=_admission(),
        safety=_safety(), snapshot=_snapshot(),
    )


# remainder intentionally preserved from current branch
