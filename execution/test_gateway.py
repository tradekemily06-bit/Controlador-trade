from datetime import datetime, timezone, timedelta

from core.ecosystem_maintenance import MaintenanceManager
from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
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


def test_gateway_does_not_downgrade_accepted_ledger_when_lifecycle_persistence_fails(tmp_path):
    class AcceptingExecutor:
        def execute(self, _request):
            return ExecutionResult(accepted=True, message="aceito", external_id="EXT-1")

    class FailingLifecycle:
        def __init__(self):
            self.records_seen = 0

        def get(self, _request_id):
            return None

        def put(self, _record):
            self.records_seen += 1
            if self.records_seen >= 2:
                raise OSError("falha de persistência")

    from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = FailingLifecycle()
    gateway = ExecutionGateway(
        AcceptingExecutor(),
        KillSwitch(),
        ledger=ledger,
        lifecycle=lifecycle,
    )

    result = gateway.execute("req-accepted-persist-failure", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ledger.status("req-accepted-persist-failure") is ExecutionLedgerStatus.ACCEPTED
    assert "Ledger permanece ACCEPTED" in result.message
    assert lifecycle.records_seen == 2


def test_recovery_cannot_return_safe_to_resume_while_execution_holds_dispatch_fence(tmp_path):
    from threading import Event, Thread
    import time

    class BlockingExecutor:
        def __init__(self):
            self.entered = Event()
            self.release = Event()

        def execute(self, request):
            self.entered.set()
            assert self.release.wait(timeout=2)
            return ExecutionResult(True, "ok")

    executor = BlockingExecutor()
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = ExecutionGateway(executor, KillSwitch(), ledger=ledger, lifecycle=lifecycle)
    recovery = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
    )
    request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=1,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        request_id="req-concurrent-recovery",
    )

    execution_result = []
    worker = Thread(target=lambda: execution_result.append(gateway.execute(request.request_id, request)))
    worker.start()
    assert executor.entered.wait(timeout=2)

    recovery_result = []
    recovery_worker = Thread(target=lambda: recovery_result.append(recovery.assess()))
    recovery_worker.start()
    time.sleep(0.1)

    # Recovery must wait for the same dispatch fence; it must never observe
    # an in-flight RESERVED/PENDING execution as SAFE_TO_RESUME.
    assert recovery_worker.is_alive()
    executor.release.set()

    worker.join(timeout=2)
    recovery_worker.join(timeout=2)
    assert not worker.is_alive()
    assert not recovery_worker.is_alive()
    assert execution_result[0].status is GatewayStatus.ACCEPTED
    assert recovery_result[0].state is not RecoveryState.SAFE_TO_RESUME
