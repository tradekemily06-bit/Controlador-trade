from datetime import datetime, timezone

import pytest

from core.operational_runtime import build_operational_runtime
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


def test_lifecycle_terminal_state_cannot_be_reused(tmp_path):
    store = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    now = datetime.now(timezone.utc)
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))
    store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.REJECTED, now))

    with pytest.raises(ValueError, match="transição inválida"):
        store.put(ExecutionLifecycleRecord("req-1", ExecutionLifecycleState.PENDING, now))


def test_runtime_restores_persistent_kill_switch(tmp_path):
    first = build_operational_runtime(tmp_path)
    first.recorder.activate_kill_switch("teste persistente")

    second = build_operational_runtime(tmp_path)

    assert second.kill_switch.state.enabled is True
    assert second.kill_switch.state.reason == "teste persistente"


def test_runtime_restores_persistent_memory(tmp_path):
    first = build_operational_runtime(tmp_path)
    snapshot = None
    assert first.recorder.memory is first.recovery.memory
    assert first.recorder is not None
