from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import pytest

from core.file_lock import exclusive_file_lock
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus


def _reserve_worker(path: str, request_id: str, ready, start, result_queue) -> None:
    ledger = ExecutionLedger(path)
    ready.put("ready")
    start.wait(10)
    try:
        ledger.reserve(request_id)
    except Exception as exc:  # worker boundary: return the exact failure class/message
        result_queue.put(("error", type(exc).__name__, str(exc)))
    else:
        result_queue.put(("ok",))


def _reconcile_worker(path: str, request_id: str, executed: bool, ready, start, result_queue) -> None:
    ledger = ExecutionLedger(path)
    ready.put("ready")
    start.wait(10)
    try:
        ledger.reconcile(
            request_id,
            executed=executed,
            evidence_id=f"evidence-{request_id}",
            evidence_source="authoritative-test-broker",
        )
    except Exception as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)))
    else:
        result_queue.put(("ok", executed))


def _transition_worker(path: str, request_id: str, target: str, ready, start, result_queue) -> None:
    ledger = ExecutionLedger(path)
    ready.put("ready")
    start.wait(10)
    try:
        if target == "accepted":
            ledger.mark_accepted(request_id)
        elif target == "unknown":
            ledger.mark_unknown(request_id)
        else:  # pragma: no cover - test-programming guard
            raise AssertionError(target)
    except Exception as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)))
    else:
        result_queue.put(("ok", target))


def _lock_holder(lock_path: str, ready) -> None:
    with exclusive_file_lock(lock_path):
        ready.put("locked")
        time.sleep(30)


def _die_after_temp_fsync(path: str, ready) -> None:
    """Simulate a crash after temp-file fsync but before os.replace()."""
    ledger = ExecutionLedger(path)
    with ledger._process_lock():  # noqa: SLF001 - adversarial interrupted-write test
        ledger._load()  # noqa: SLF001
        ledger._states["crash-only"] = ExecutionLedgerStatus.RESERVED  # noqa: SLF001
        ledger.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = ledger.path.with_name(f".{ledger.path.name}.tmp")
        payload = {
            "states": {key: value.value for key, value in sorted(ledger._states.items())},  # noqa: SLF001
            "reconciliation_evidence": {},
            "execution_context": {},
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        ready.put("fsynced")
        os._exit(92)


def _join_all(processes: list[mp.Process]) -> None:
    for process in processes:
        process.join(15)
        if process.is_alive():
            process.terminate()
            process.join(5)
        assert process.exitcode is not None


def _start_race(processes: list[mp.Process], ready, start) -> None:
    for _ in processes:
        assert ready.get(timeout=10) == "ready"
    start.set()
    _join_all(processes)


def test_multiprocess_reservation_allows_exactly_one_winner(tmp_path: Path):
    ctx = mp.get_context("fork")
    path = tmp_path / "ledger.json"
    ready = ctx.Queue()
    results = ctx.Queue()
    start = ctx.Event()
    processes = [
        ctx.Process(target=_reserve_worker, args=(str(path), "same-request", ready, start, results)),
        ctx.Process(target=_reserve_worker, args=(str(path), "same-request", ready, start, results)),
    ]
    for process in processes:
        process.start()
    _start_race(processes, ready, start)

    outcomes = [results.get(timeout=5) for _ in processes]
    assert sum(outcome[0] == "ok" for outcome in outcomes) == 1
    assert sum(outcome[0] == "error" for outcome in outcomes) == 1
    assert ExecutionLedger(path).status("same-request") is ExecutionLedgerStatus.RESERVED


def test_multiprocess_reconciliation_allows_exactly_one_terminal_transition(tmp_path: Path):
    ctx = mp.get_context("fork")
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("uncertain")
    ledger.mark_unknown("uncertain")

    ready = ctx.Queue()
    results = ctx.Queue()
    start = ctx.Event()
    processes = [
        ctx.Process(target=_reconcile_worker, args=(str(path), "uncertain", True, ready, start, results)),
        ctx.Process(target=_reconcile_worker, args=(str(path), "uncertain", False, ready, start, results)),
    ]
    for process in processes:
        process.start()
    _start_race(processes, ready, start)

    outcomes = [results.get(timeout=5) for _ in processes]
    assert sum(outcome[0] == "ok" for outcome in outcomes) == 1
    assert sum(outcome[0] == "error" for outcome in outcomes) == 1
    assert ExecutionLedger(path).status("uncertain") in {
        ExecutionLedgerStatus.RECONCILED_EXECUTED,
        ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED,
    }


def test_multiprocess_conflicting_transitions_allow_only_one_winner(tmp_path: Path):
    ctx = mp.get_context("fork")
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("conflict")

    ready = ctx.Queue()
    results = ctx.Queue()
    start = ctx.Event()
    processes = [
        ctx.Process(target=_transition_worker, args=(str(path), "conflict", "accepted", ready, start, results)),
        ctx.Process(target=_transition_worker, args=(str(path), "conflict", "unknown", ready, start, results)),
    ]
    for process in processes:
        process.start()
    _start_race(processes, ready, start)

    outcomes = [results.get(timeout=5) for _ in processes]
    assert sum(outcome[0] == "ok" for outcome in outcomes) == 1
    assert sum(outcome[0] == "error" for outcome in outcomes) == 1
    assert ExecutionLedger(path).status("conflict") in {
        ExecutionLedgerStatus.ACCEPTED,
        ExecutionLedgerStatus.UNKNOWN,
    }


def test_new_process_can_assume_lock_after_abrupt_holder_termination(tmp_path: Path):
    if not hasattr(__import__("fcntl"), "flock"):
        pytest.skip("OS-level flock is required by the production lock")

    ctx = mp.get_context("fork")
    path = tmp_path / "ledger.json"
    lock_path = path.with_name(f".{path.name}.lock")
    ready = ctx.Queue()
    holder = ctx.Process(target=_lock_holder, args=(str(lock_path), ready))
    holder.start()
    assert ready.get(timeout=10) == "locked"
    holder.terminate()
    holder.join(10)
    assert holder.exitcode is not None

    ledger = ExecutionLedger(path)
    ledger.reserve("after-crash")
    assert ledger.status("after-crash") is ExecutionLedgerStatus.RESERVED


def test_interrupted_write_preserves_last_committed_ledger(tmp_path: Path):
    if not hasattr(__import__("fcntl"), "flock"):
        pytest.skip("OS-level flock is required by the production lock")

    ctx = mp.get_context("fork")
    path = tmp_path / "ledger.json"
    baseline = ExecutionLedger(path)
    baseline.reserve("baseline")

    ready = ctx.Queue()
    crashed = ctx.Process(target=_die_after_temp_fsync, args=(str(path), ready))
    crashed.start()
    assert ready.get(timeout=10) == "fsynced"
    crashed.join(10)
    assert crashed.exitcode == 92

    restored = ExecutionLedger(path)
    assert restored.status("baseline") is ExecutionLedgerStatus.RESERVED
    assert restored.status("crash-only") is None
    restored.reserve("after-interrupted-write")
    assert restored.status("after-interrupted-write") is ExecutionLedgerStatus.RESERVED
    assert restored.path.with_name(f".{restored.path.name}.tmp").exists()
