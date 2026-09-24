from datetime import datetime, timezone

from core.models import Signal
from core.operation_memory import OperationMemoryRecord

import pytest

from core.operational_runtime import build_operational_runtime
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


def test_runtime_restores_persistent_kill_switch(tmp_path):
    first = build_operational_runtime(tmp_path)
    first.recorder.activate_kill_switch("teste persistente")

    second = build_operational_runtime(tmp_path)

    assert second.kill_switch.state.enabled is True
    assert second.kill_switch.state.reason == "teste persistente"


def test_runtime_restores_persistent_memory(tmp_path):
    first = build_operational_runtime(tmp_path)
    record = OperationMemoryRecord(
        timestamp=datetime.now(timezone.utc), signal=Signal.COMPRA, score=80,
        decision="COMPRA", reason="teste", result="PENDENTE", symbol="EURUSD",
        timeframe="5m", quality_score=80, quality_level="ALTA", entry_conditions=(),
    )
    first.recorder.memory.append(record)
    first.recorder.store.save(first.recorder.memory)

    second = build_operational_runtime(tmp_path)

    assert second.recorder.memory.records()[0] == record
    assert second.recorder.memory is second.recovery.memory
