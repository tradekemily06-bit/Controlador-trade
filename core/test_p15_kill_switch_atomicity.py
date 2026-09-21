from __future__ import annotations

import threading

from core.persistent_operational_recorder import PersistentOperationalRecorder


def test_kill_switch_activation_holds_canonical_fence_through_synchronization(tmp_path):
    recorder = PersistentOperationalRecorder.from_path(
        tmp_path / "operations.json",
        safety_path=tmp_path / "safety.json",
    )
    entered = threading.Event()
    release = threading.Event()
    original = recorder.kill_switch.synchronize_under_change_fence

    def blocked_synchronize(state):
        entered.set()
        assert release.wait(2)
        return original(state)

    recorder.kill_switch.synchronize_under_change_fence = blocked_synchronize  # type: ignore[method-assign]
    worker = threading.Thread(
        target=recorder.activate_kill_switch,
        args=("race-test",),
    )
    worker.start()
    assert entered.wait(2)

    acquired = threading.Event()

    def competing_writer():
        with recorder.safety_store.coordination_lock():
            acquired.set()

    competitor = threading.Thread(target=competing_writer)
    competitor.start()

    # The durable safety write has happened, but the in-memory gate has not
    # yet synchronized. The canonical fence must still exclude dispatch/state
    # writers during this interval.
    assert not acquired.wait(0.1)

    release.set()
    worker.join(2)
    competitor.join(2)

    assert not worker.is_alive()
    assert not competitor.is_alive()
    assert acquired.is_set()
    assert recorder.kill_switch.state.enabled is True
    assert recorder.kill_switch.state.reason == "race-test"


def test_kill_switch_persistence_can_run_under_existing_coordination_fence(tmp_path):
    recorder = PersistentOperationalRecorder.from_path(
        tmp_path / "operations.json",
        safety_path=tmp_path / "safety.json",
    )
    with recorder.safety_store.coordination_lock():
        state = recorder.safety_store.set_kill_switch_under_coordination_fence(
            enabled=True,
            reason="under-fence-test",
        )
        recorder.kill_switch.synchronize_under_change_fence(state)

    assert recorder.kill_switch.state.enabled is True
    assert recorder.kill_switch.state.reason == "under-fence-test"


def test_gateway_final_dispatch_does_not_reacquire_safety_fence(tmp_path):
    from core.decision_snapshot import DecisionSnapshot
    from core.kill_switch import KillSwitch
    from core.operational_safety_store import OperationalSafetyStore
    from execution.gateway import ExecutionGateway
    from execution.ports import ExecutionRequest, ExecutionMode, ExecutionResult
    from core.models import Signal

    class Executor:
        def execute(self, request):
            return ExecutionResult(True, "demo-ok", external_id="demo-1")

    safety_store = OperationalSafetyStore(tmp_path / "safety.json")
    kill_switch = KillSwitch(change_fence=safety_store.coordination_lock)
    gateway = ExecutionGateway(Executor(), kill_switch, safety_store=safety_store)

    request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=1.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )
    result = gateway.execute("nested-fence-test", request)

    assert result.accepted is True
