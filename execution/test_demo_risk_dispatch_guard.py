from datetime import datetime, timezone

from core.demo_risk_state_store import DemoRiskStateStore
from core.operational_state import OperationalState
from core.risk_state_fingerprint import risk_state_fingerprint
from execution.demo_risk_dispatch_guard import DemoRiskDispatchGuard
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def make_state(trades_today=0):
    return OperationalState(
        balance=1000.0,
        equity=1000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        trades_today=trades_today,
        consecutive_losses=0,
        open_positions=0,
        net_position=0.0,
        exposure=0.0,
        market_open=True,
        last_processed_candle=datetime(2026, 9, 15, 19, 0, tzinfo=timezone.utc),
    )


def request(fingerprint):
    from core.models import Signal

    return ExecutionRequest(
        mode=ExecutionMode.DEMO,
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        risk_state_fingerprint=fingerprint,
    )


def test_guard_revalidates_risk_under_shared_dispatch_lock(tmp_path):
    store = DemoRiskStateStore(tmp_path / "risk.json")
    first = make_state(0)
    fingerprint = store.replace(first, source="demo-account-adapter")
    executor = PaperExecutor()
    guard = DemoRiskDispatchGuard(
        executor,
        risk_store=store,
        risk_fingerprint_provider=store.fingerprint,
    )

    result = guard.execute(request(fingerprint))

    assert result.accepted is True
    assert len(executor.executions()) == 1


def test_guard_blocks_changed_risk_before_executor(tmp_path):
    store = DemoRiskStateStore(tmp_path / "risk.json")
    first = make_state(0)
    fingerprint = store.replace(first, source="demo-account-adapter")
    store.replace(make_state(1), source="reconciliation")
    executor = PaperExecutor()
    guard = DemoRiskDispatchGuard(
        executor,
        risk_store=store,
        risk_fingerprint_provider=store.fingerprint,
    )

    result = guard.execute(request(fingerprint))

    assert result.accepted is False
    assert "estado de risco mudou" in result.message
    assert executor.executions() == ()


def test_guard_does_not_invent_risk_identity_when_request_has_none(tmp_path):
    store = DemoRiskStateStore(tmp_path / "risk.json")
    store.replace(make_state(), source="demo-account-adapter")
    executor = PaperExecutor()
    guard = DemoRiskDispatchGuard(
        executor,
        risk_store=store,
        risk_fingerprint_provider=store.fingerprint,
    )

    result = guard.execute(request(None))

    assert result.accepted is True
    assert len(executor.executions()) == 1
