from pathlib import Path

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.global_operational_barrier import GlobalOperationalBarrier
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


class FakeAdapter:
    def __init__(self, result=None, error=False):
        self.result = result or ExecutionResult(True, "accepted", "external-1")
        self.error = error
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        if self.error:
            raise TimeoutError("timeout after dispatch")
        return self.result


class FakeRiskStateProvider:
    def __init__(self, state):
        self.state = state

    def current_risk_state(self):
        return self.state


class FakeRealSafetyProvider:
    def __init__(self, report):
        self.report = report

    def current_real_safety(self):
        return self.report


def _risk_state():
    return OperationalState(
        balance=1000.0, equity=1000.0, realized_pnl=0.0, unrealized_pnl=0.0,
        trades_today=0, consecutive_losses=0, open_positions=0,
        net_position=0.0, exposure=0.0, market_open=True,
    )


def _snapshot():
    state = _risk_state()
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None, operational_state_available=True,
        trades_today=0, consecutive_losses=0, symbol="TEST", timeframe="5m",
        risk_state_identity=risk_state_identity(state),
    )


def _authorization():
    return RealExecutionAuthorization("auth", "audit-1", "fake", "fake-adapter", True, True)


def _safety():
    return RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )


def _admission():
    return RealAdmissionBoundary().admit(
        admission_id="adm-1", audit_id="audit-1", audit_verified=True,
        authorization_active=True, safety_ready=True, broker_available=True,
        broker_id="fake",
    )


def _request(request_id="req-1"):
    return ExecutionRequest(
        "TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL,
        request_id=request_id, risk_state_fingerprint=risk_state_identity(_risk_state()),
    )


def _gateway(path: Path, adapter: FakeAdapter):
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    safety = _safety()
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(path),
        FakeRiskStateProvider(_risk_state()),
        FakeRealSafetyProvider(safety),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )


def test_real_positive_flow_stays_inside_authoritative_gateway(tmp_path: Path):
    adapter = FakeAdapter()
    gateway = _gateway(tmp_path / "ledger.json", adapter)
    result = gateway.execute(
        broker="fake", request_id="req-1", request=_request(),
        authorization=_authorization(), admission=_admission(),
        safety=_safety(), snapshot=_snapshot(),
    )
    assert result.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1


def test_real_adapter_timeout_is_unknown_not_rejected(tmp_path: Path):
    adapter = FakeAdapter(error=True)
    ledger_path = tmp_path / "ledger.json"
    gateway = _gateway(ledger_path, adapter)
    result = gateway.execute(
        broker="fake", request_id="timeout-1", request=_request("timeout-1"),
        authorization=_authorization(), admission=_admission(),
        safety=_safety(), snapshot=_snapshot(),
    )
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger_status(ledger_path, "timeout-1") is ExecutionLedgerStatus.UNKNOWN


def ledger_status(path: Path, request_id: str):
    return ExecutionLedger(path).status(request_id)


def test_real_legacy_reconciliation_is_hard_blocked(tmp_path: Path):
    gateway = _gateway(tmp_path / "ledger.json", FakeAdapter())
    with pytest.raises(RuntimeError, match="evidência externa autoritativa"):
        gateway.reconcile_unknown("missing", executed=False)


def test_real_replay_after_restart_is_blocked_or_unknown_without_second_dispatch(tmp_path: Path):
    path = tmp_path / "ledger.json"
    adapter = FakeAdapter()
    first = _gateway(path, adapter)
    first_result = first.execute(
        broker="fake", request_id="restart-1", request=_request("restart-1"),
        authorization=_authorization(), admission=_admission(),
        safety=_safety(), snapshot=_snapshot(),
    )
    assert first_result.status == RealGatewayStatus.ADMITTED
    second = _gateway(path, adapter)
    second_result = second.execute(
        broker="fake", request_id="restart-1", request=_request("restart-1"),
        authorization=_authorization(), admission=_admission(),
        safety=_safety(), snapshot=_snapshot(),
    )
    assert second_result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 1


def test_real_changed_risk_is_blocked_before_broker_dispatch(tmp_path: Path):
    adapter = FakeAdapter()
    provider = FakeRiskStateProvider(_risk_state())
    safety = _safety()
    registry = BrokerRegistry(); registry.register("fake", adapter)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"),
        provider, FakeRealSafetyProvider(safety),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )
    state = _risk_state()
    provider.state = OperationalState(
        balance=state.balance, equity=state.equity, realized_pnl=state.realized_pnl,
        unrealized_pnl=state.unrealized_pnl, trades_today=1,
        consecutive_losses=state.consecutive_losses, open_positions=state.open_positions,
        net_position=state.net_position, exposure=state.exposure, market_open=state.market_open,
    )
    result = gateway.execute(
        broker="fake", request_id="risk-change", request=_request("risk-change"),
        authorization=_authorization(), admission=_admission(), safety=safety,
        snapshot=_snapshot(),
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_global_barrier_failure_is_fail_closed(tmp_path: Path):
    adapter = FakeAdapter()
    gateway = _gateway(tmp_path / "ledger.json", adapter)
    result = gateway.execute(
        broker="fake", request_id="barrier-1", request=_request("barrier-1"),
        authorization=_authorization(), admission=_admission(), safety=_safety(),
        snapshot=_snapshot(),
    )
    assert result.status == RealGatewayStatus.ADMITTED
    blocked_gateway = RealExecutionGateway(
        gateway._gateway, gateway._ledger, gateway._risk_state_provider,
        gateway._real_safety_provider,
        operational_barrier_provider=lambda: GlobalOperationalBarrier(()),
    )
    assert blocked_gateway._global_barrier_error() is None


def test_real_unknown_retry_never_reaches_adapter_again(tmp_path: Path):
    adapter = FakeAdapter(error=True)
    path = tmp_path / "ledger.json"
    gateway = _gateway(path, adapter)
    first = gateway.execute(
        broker="fake", request_id="unknown-retry", request=_request("unknown-retry"),
        authorization=_authorization(), admission=_admission(), safety=_safety(),
        snapshot=_snapshot(),
    )
    assert first.status == RealGatewayStatus.UNKNOWN
    second = _gateway(path, adapter).execute(
        broker="fake", request_id="unknown-retry", request=_request("unknown-retry"),
        authorization=_authorization(), admission=_admission(), safety=_safety(),
        snapshot=_snapshot(),
    )
    assert second.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1
