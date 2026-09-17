from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.kill_switch import KillSwitch
from execution.execution_lifecycle import ExecutionLifecycleState, ExecutionLifecycleStore
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal


def request():
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def blocked_barrier():
    return GlobalOperationalBarrier(
        [SafetyComponent(name="test-gate", healthy=False, detail="gate bloqueado")]
    )


def test_pre_dispatch_barrier_block_is_known_rejection_not_unknown(tmp_path):
    executor = PaperExecutor()
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = ExecutionGateway(
        executor,
        KillSwitch(),
        lifecycle=lifecycle,
        operational_barrier_provider=blocked_barrier,
    )

    result = gateway.execute("req-pre-block", request())

    assert result.status is GatewayStatus.BLOCKED
    assert executor.executions() == ()
    record = lifecycle.get("req-pre-block")
    assert record is not None
    assert record.state is ExecutionLifecycleState.REJECTED
    assert "barreira" in record.message.lower()


def test_pre_dispatch_block_does_not_become_reconciliation_unknown(tmp_path):
    executor = PaperExecutor()
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = ExecutionGateway(
        executor,
        KillSwitch(),
        lifecycle=lifecycle,
        operational_barrier_provider=blocked_barrier,
    )

    result = gateway.execute("req-known-block", request())

    assert result.status is GatewayStatus.BLOCKED
    record = lifecycle.get("req-known-block")
    assert record is not None
    assert record.state is not ExecutionLifecycleState.UNKNOWN
