from pathlib import Path
import subprocess
import sys
import textwrap
import time

from execution.execution_coordination import ExecutionCoordinationLock
from execution.execution_ledger import ExecutionLedger
from datetime import datetime, timezone

from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore


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
    canonical = state / "ledger.json"
    alias = state / "." / "ledger.json"

    first = ExecutionLifecycleStore(alias)
    second = ExecutionLifecycleStore(canonical)

    assert first.path == second.path


def test_coordination_lock_serializes_independent_processes(tmp_path: Path):
    lock_path = tmp_path / "execution-ledger.json"
    ready = tmp_path / "first-ready"
    release = tmp_path / "release-first"
    acquired = tmp_path / "second-acquired"

    child = textwrap.dedent(
        """
        import sys
        import time
        from pathlib import Path
        from execution.execution_coordination import ExecutionCoordinationLock

        lock = ExecutionCoordinationLock(sys.argv[1])
        ready = Path(sys.argv[2])
        release = Path(sys.argv[3])

        with lock.acquire():
            ready.write_text("ready")
            while not release.exists():
                time.sleep(0.02)
        """
    )
    first = subprocess.Popen(
        [sys.executable, "-c", child, str(lock_path), str(ready), str(release)]
    )
    second = None
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "first process did not acquire coordination lock"

        child_second = textwrap.dedent(
            """
            import sys
            from pathlib import Path
            from execution.execution_coordination import ExecutionCoordinationLock

            lock = ExecutionCoordinationLock(sys.argv[1])
            acquired = Path(sys.argv[2])

            with lock.acquire():
                acquired.write_text("acquired")
            """
        )
        second = subprocess.Popen(
            [sys.executable, "-c", child_second, str(lock_path), str(acquired)]
        )

        time.sleep(0.25)
        assert not acquired.exists(), "second process bypassed the coordination lock"

        release.write_text("release")
        assert second.wait(timeout=10) == 0
        assert acquired.exists()
        assert first.wait(timeout=10) == 0
    finally:
        release.write_text("release")
        if second is not None and second.poll() is None:
            second.kill()
            second.wait(timeout=5)
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)


def test_ledger_cross_process_same_request_id_allows_only_one_reservation(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    child = textwrap.dedent(
        """
        import sys
        from execution.execution_ledger import ExecutionLedger
        try:
            ExecutionLedger(sys.argv[1]).reserve("same-request")
        except ValueError:
            raise SystemExit(3)
        """
    )
    first = subprocess.Popen([sys.executable, "-c", child, str(ledger_path)])
    second = subprocess.Popen([sys.executable, "-c", child, str(ledger_path)])
    assert {first.wait(timeout=10), second.wait(timeout=10)} == {0, 3}
    assert ExecutionLedger(ledger_path).records() == ("same-request",)


def test_lifecycle_cross_process_terminal_transition_cannot_regress(tmp_path: Path):
    lifecycle_path = tmp_path / "lifecycle.json"
    lifecycle = ExecutionLifecycleStore(lifecycle_path)
    lifecycle.put(
        ExecutionLifecycleRecord(
            "shared-request",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
        )
    )
    child = textwrap.dedent(
        """
        import sys
        from datetime import datetime, timezone
        from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
        store = ExecutionLifecycleStore(sys.argv[1])
        state = ExecutionLifecycleState.ACCEPTED if sys.argv[2] == "accepted" else ExecutionLifecycleState.REJECTED
        try:
            store.put(ExecutionLifecycleRecord("shared-request", state, datetime.now(timezone.utc)))
        except ValueError:
            raise SystemExit(3)
        """
    )
    first = subprocess.Popen([sys.executable, "-c", child, str(lifecycle_path), "accepted"])
    second = subprocess.Popen([sys.executable, "-c", child, str(lifecycle_path), "rejected"])
    results = {first.wait(timeout=10), second.wait(timeout=10)}
    assert results == {0, 3}
    assert ExecutionLifecycleStore(lifecycle_path).get("shared-request").state in (
        ExecutionLifecycleState.ACCEPTED,
        ExecutionLifecycleState.REJECTED,
    )
