from pathlib import Path
from threading import Event, Thread

from core.kill_switch import KillSwitch
from core.operational_safety_store import OperationalSafetyStore
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionRequest, ExecutionResult, ExecutionMode
from core.models import Signal


def request(request_id: str = "req-fence") -> ExecutionRequest:
    return ExecutionRequest(
        request_id=request_id,
        symbol="BTCUSD",
        signal=Signal.COMPRA,
        amount=1.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def test_safety_store_exposes_same_coordination_fence_used_by_gateway(tmp_path: Path):
    safety = OperationalSafetyStore(tmp_path / "operational-safety.json")
    gateway = ExecutionGateway(
        PaperExecutor(),
        KillSwitch(),
        safety_store=safety,
    )

    assert gateway._dispatch_lock_path == safety.coordination_lock_path


def test_gateway_never_downgrades_in_memory_active_kill_switch_from_stale_disk_clear(tmp_path: Path):
    safety = OperationalSafetyStore(tmp_path / "operational-safety.json")
    safety.set_kill_switch(enabled=False)
    kill_switch = KillSwitch()
    kill_switch.activate("emergency")
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, kill_switch, safety_store=safety)

    result = gateway.execute("req-stale-clear", request("req-stale-clear"))

    assert result.status is GatewayStatus.BLOCKED
    assert "não foi persistido" in result.message
    assert executor.executions() == ()


def test_kill_switch_activation_waits_for_dispatch_fence(tmp_path: Path):
    safety = OperationalSafetyStore(tmp_path / "operational-safety.json")
    kill_switch = KillSwitch()
    executor_started = Event()
    release_executor = Event()

    class BlockingExecutor:
        def execute(self, _request):
            executor_started.set()
            assert release_executor.wait(timeout=5)
            return ExecutionResult(True, "demo accepted", "PAPER-FENCE")

    gateway = ExecutionGateway(
        BlockingExecutor(),
        kill_switch,
        safety_store=safety,
    )

    result_holder = {}

    def run_dispatch():
        result_holder["result"] = gateway.execute("req-fence", request())

    dispatch_thread = Thread(target=run_dispatch)
    dispatch_thread.start()
    assert executor_started.wait(timeout=5)

    activation_done = Event()

    def activate():
        kill_switch.activate("emergency")
        activation_done.set()

    activation_thread = Thread(target=activate)
    activation_thread.start()

    assert not activation_done.wait(timeout=0.2)
    # The state mutation itself must be fenced, not only its persistence callback.
    assert kill_switch.state.enabled is False

    release_executor.set()
    dispatch_thread.join(timeout=5)
    activation_thread.join(timeout=5)

    assert not dispatch_thread.is_alive()
    assert not activation_thread.is_alive()
    assert result_holder["result"].status is GatewayStatus.ACCEPTED
    assert activation_done.is_set()

    blocked = gateway.execute("req-after-fence", request("req-after-fence"))
    assert blocked.status is GatewayStatus.BLOCKED


def test_kill_switch_synchronize_waits_for_dispatch_fence(tmp_path: Path):
    safety = OperationalSafetyStore(tmp_path / "operational-safety.json")
    kill_switch = KillSwitch(change_fence=safety.coordination_lock)
    executor_started = Event()
    release_executor = Event()

    class BlockingExecutor:
        def execute(self, _request):
            executor_started.set()
            assert release_executor.wait(timeout=5)
            return ExecutionResult(True, "demo accepted", "PAPER-SYNC-FENCE")

    gateway = ExecutionGateway(BlockingExecutor(), kill_switch, safety_store=safety)

    dispatch_thread = Thread(target=lambda: gateway.execute("req-sync-fence", request("req-sync-fence")))
    dispatch_thread.start()
    assert executor_started.wait(timeout=5)

    sync_done = Event()

    def synchronize():
        kill_switch.synchronize(type(kill_switch.state)(enabled=True, reason="external safety state"))
        sync_done.set()

    sync_thread = Thread(target=synchronize)
    sync_thread.start()
    assert not sync_done.wait(timeout=0.2)
    assert kill_switch.state.enabled is False

    release_executor.set()
    dispatch_thread.join(timeout=5)
    sync_thread.join(timeout=5)

    assert not dispatch_thread.is_alive()
    assert not sync_thread.is_alive()
    assert sync_done.is_set()
    assert kill_switch.state.enabled is True
