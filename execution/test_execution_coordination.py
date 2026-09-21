from pathlib import Path

from execution.execution_coordination import ExecutionCoordinationLock
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore


def test_coordination_lock_canonicalizes_equivalent_paths(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir()
    canonical = state / "ledger.json"
    alias = state / "." / "ledger.json"

    first = ExecutionCoordinationLock(canonical)
    second = ExecutionCoordinationLock(alias)

    assert first.path == second.path
    assert first.lock_path == second.lock_path


def test_ledger_canonicalizes_equivalent_paths(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir()
    canonical = state / "ledger.json"
    alias = state / "." / "ledger.json"

    first = ExecutionLedger(canonical)
    second = ExecutionLedger(alias)

    first.reserve("same-state")
    assert second.status("same-state") is not None
    assert first.path == second.path


def test_lifecycle_canonicalizes_equivalent_paths(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir()
    canonical = state / "lifecycle.json"
    alias = state / "." / "lifecycle.json"

    first = ExecutionLifecycleStore(canonical)
    second = ExecutionLifecycleStore(alias)

    assert first.path == second.path
