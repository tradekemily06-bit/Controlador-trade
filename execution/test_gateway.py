from datetime import datetime, timezone, timedelta

from core.ecosystem_maintenance import MaintenanceManager
from core.recovery_coordinator import RecoveryCoordinator, RecoveryState
from core.runtime_checkpoint import RuntimeCheckpointStore
from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


def request(signal=Signal.COMPRA, mode=ExecutionMode.DEMO):
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=signal,
        amount=10.0,
        duration_seconds=60,
        mode=mode,
    )


def test_gateway_executes_valid_demo_request():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.ACCEPTED
    assert result.execution is not None
    assert result.execution.external_id == "PAPER-000001"


def test_gateway_blocks_active_kill_switch_before_executor():
    executor = PaperExecutor()
    kill_switch = KillSwitch()
    kill_switch.activate("emergência")
    gateway = ExecutionGateway(executor, kill_switch)

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.BLOCKED
    assert executor.executions() == ()


def test_gateway_rejects_real_mode_in_p5():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    result = gateway.execute("req-1", request(mode=ExecutionMode.REAL))

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_rejects_wait_signal():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    result = gateway.execute("req-1", request(signal=Signal.AGUARDAR))

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_rejects_duplicate_request_id():
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch())

    first = gateway.execute("req-1", request())
    second = gateway.execute("req-1", request())

    assert first.status is GatewayStatus.ACCEPTED
    assert second.status is GatewayStatus.DUPLICATE
    assert len(executor.executions()) == 1


def test_gateway_does_not_mark_invalid_request_as_processed():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    invalid = gateway.execute("req-1", request(mode=ExecutionMode.REAL))
    valid = gateway.execute("req-1", request())

    assert invalid.status is GatewayStatus.INVALID_REQUEST
    assert valid.status is GatewayStatus.ACCEPTED


def test_gateway_rejects_empty_request_id():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    result = gateway.execute("   ", request())

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_fails_closed_when_executor_raises():
    class BrokenExecutor:
        def execute(self, _request):
            raise RuntimeError("falha simulada")

    gateway = ExecutionGateway(BrokenExecutor(), KillSwitch())

    result = gateway.execute("req-1", request())
    retry = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert retry.status is GatewayStatus.EXECUTOR_ERROR


def test_gateway_rejects_invalid_executor_result():
    class InvalidExecutor:
        def execute(self, _request):
            return "not-an-execution-result"

    gateway = ExecutionGateway(InvalidExecutor(), KillSwitch())

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR


def test_gateway_requires_executor():
    try:
        ExecutionGateway(None, KillSwitch())
    except ValueError as exc:
        assert "executor" in str(exc)
    else:
        raise AssertionError("gateway deveria exigir executor")


def test_executor_rejection_is_not_reported_as_accepted():
    class RejectingExecutor:
        def execute(self, _request):
            return ExecutionResult(accepted=False, message="rejeitado")

    gateway = ExecutionGateway(RejectingExecutor(), KillSwitch())

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.EXECUTION_REJECTED
    assert not result.accepted


def test_gateway_blocks_active_maintenance_before_executor():
    now = datetime.now(timezone.utc)
    maintenance = MaintenanceManager()
    maintenance.schedule(
        maintenance_id="maint-1",
        title="Atualização",
        message="Manutenção programada",
        starts_at=now + timedelta(minutes=5),
        duration_minutes=30,
        now=now,
    )
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), maintenance=maintenance)

    scheduled = gateway.execute("req-scheduled", request(), timestamp=now + timedelta(minutes=2))

    assert scheduled.status is GatewayStatus.ACCEPTED

    active_window = maintenance._current.__class__(
        **{**maintenance._current.__dict__, "starts_at": now - timedelta(minutes=1), "ends_at": now + timedelta(minutes=30)}
    )
    maintenance._current = active_window
    active = gateway.execute("req-active", request(), timestamp=now - timedelta(days=1))

    assert active.status is GatewayStatus.BLOCKED
    assert len(executor.executions()) == 1


def test_gateway_allows_execution_after_maintenance_completes():
    now = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)
    maintenance = MaintenanceManager()
    maintenance.schedule(
        maintenance_id="maint-1",
        title="Atualização",
        message="Manutenção programada",
        starts_at=now + timedelta(minutes=5),
        duration_minutes=10,
        now=now,
    )
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), maintenance=maintenance)

    result = gateway.execute("req-after", request(), timestamp=now + timedelta(minutes=20))

    assert result.status is GatewayStatus.ACCEPTED


def test_gateway_rechecks_maintenance_after_persistence_before_executor():
    class ActivatesOnFinalCheck:
        def __init__(self):
            self.calls = 0

        def execution_blocked(self, *, now):
            self.calls += 1
            return self.calls >= 2

    maintenance = ActivatesOnFinalCheck()
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), maintenance=maintenance)

    result = gateway.execute("req-final-maintenance", request())

    assert result.status is GatewayStatus.BLOCKED
    assert executor.executions() == ()


def test_gateway_final_maintenance_barrier_ignores_stale_decision_timestamp():
    now = datetime.now(timezone.utc)
    maintenance = MaintenanceManager()
    maintenance.schedule(
        maintenance_id="maint-live",
        title="Atualização crítica",
        message="Manutenção em andamento",
        starts_at=now - timedelta(minutes=1),
        duration_minutes=30,
        now=now - timedelta(minutes=2),
    )
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), maintenance=maintenance)

    result = gateway.execute(
        "req-stale-decision",
        request(),
        timestamp=now - timedelta(minutes=5),
    )

    assert result.status is GatewayStatus.BLOCKED
    assert executor.executions() == ()


def test_gateway_rejects_non_finite_or_boolean_amount_and_duration():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    for amount in (True, float("nan"), float("inf"), float("-inf")):
        invalid = ExecutionRequest(
            symbol="BTCUSD",
            signal=Signal.COMPRA,
            amount=amount,
            duration_seconds=60,
            mode=ExecutionMode.DEMO,
        )
        assert gateway.execute("req-amount-" + str(amount), invalid).status is GatewayStatus.INVALID_REQUEST

    for duration in (True, 0, -1):
        invalid = ExecutionRequest(
            symbol="BTCUSD",
            signal=Signal.COMPRA,
            amount=10.0,
            duration_seconds=duration,
            mode=ExecutionMode.DEMO,
        )
        assert gateway.execute("req-duration-" + str(duration), invalid).status is GatewayStatus.INVALID_REQUEST


def test_gateway_persistence_failure_after_broker_acceptance_blocks_restart_resume(tmp_path):
    class LifecycleFailsAfterBrokerAcceptance(ExecutionLifecycleStore):
        def put(self, record):
            if record.state is ExecutionLifecycleState.ACCEPTED:
                raise OSError("falha simulada de persistência")
            return super().put(record)

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = LifecycleFailsAfterBrokerAcceptance(tmp_path / "lifecycle.json")
    gateway = ExecutionGateway(
        PaperExecutor(),
        KillSwitch(),
        ledger=ledger,
        lifecycle=lifecycle,
    )

    result = gateway.execute("req-persist-fail", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ledger.status("req-persist-fail") is ExecutionLedgerStatus.ACCEPTED
    assert lifecycle.get("req-persist-fail").state is ExecutionLifecycleState.UNKNOWN

    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
    )
    assessment = recovery.assess()
    assert assessment.state is RecoveryState.REQUIRES_RECONCILIATION
    assert assessment.can_resume is False
