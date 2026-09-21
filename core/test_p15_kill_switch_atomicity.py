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
    original = recorder.kill_switch.synchronize

    def blocked_synchronize(state):
        entered.set()
        assert release.wait(2)
        return original(state)

    recorder.kill_switch.synchronize = blocked_synchronize  # type: ignore[method-assign]
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
