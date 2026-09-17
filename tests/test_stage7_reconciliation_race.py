from __future__ import annotations

import multiprocessing
from pathlib import Path

from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus


def _prepare_unknown(path: str) -> None:
    ledger = ExecutionLedger(Path(path))
    ledger.reserve_real("req-race", broker_id="fake", symbol="TEST")
    ledger.mark_unknown("req-race")


def _race_reconcile(path: str, start_event, result_queue) -> None:
    start_event.wait(timeout=10)
    try:
        ExecutionLedger(Path(path)).reconcile(
            "req-race",
            executed=True,
            evidence_id="external-race",
            evidence_source="fake-broker-query",
        )
        result_queue.put("RECONCILED")
    except Exception as exc:  # pragma: no cover - child reports outcome
        result_queue.put(type(exc).__name__)


def _race_retry(path: str, start_event, result_queue) -> None:
    start_event.wait(timeout=10)
    try:
        ExecutionLedger(Path(path)).reserve_real(
            "req-race",
            broker_id="fake",
            symbol="TEST",
        )
        result_queue.put("RETRY_RESERVED")
    except Exception as exc:  # pragma: no cover - child reports outcome
        result_queue.put(type(exc).__name__)


def _race_duplicate_reconcile(path: str, start_event, result_queue) -> None:
    start_event.wait(timeout=10)
    try:
        ExecutionLedger(Path(path)).reconcile(
            "req-race",
            executed=True,
            evidence_id="external-race",
            evidence_source="fake-broker-query",
        )
        result_queue.put("RECONCILED")
    except Exception as exc:  # pragma: no cover - child reports outcome
        result_queue.put(type(exc).__name__)


def test_unknown_cannot_race_with_new_reservation_across_processes(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    _prepare_unknown(str(ledger_path))

    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(target=_race_reconcile, args=(str(ledger_path), start_event, result_queue)),
        context.Process(target=_race_retry, args=(str(ledger_path), start_event, result_queue)),
    ]
    for process in processes:
        process.start()
    start_event.set()
    results = sorted(result_queue.get(timeout=15) for _ in processes)
    for process in processes:
        process.join(timeout=15)

    assert results == ["RECONCILED", "ValueError"]
    assert ExecutionLedger(ledger_path).status("req-race") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert all(process.exitcode == 0 for process in processes)


def test_reconciliation_itself_is_single_winner_across_processes(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    _prepare_unknown(str(ledger_path))

    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(target=_race_duplicate_reconcile, args=(str(ledger_path), start_event, result_queue))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start_event.set()
    results = sorted(result_queue.get(timeout=15) for _ in processes)
    for process in processes:
        process.join(timeout=15)

    assert results == ["RECONCILED", "ValueError"]
    ledger = ExecutionLedger(ledger_path)
    assert ledger.status("req-race") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ledger.reconciliation_evidence("req-race") == {
        "evidence_id": "external-race",
        "evidence_source": "fake-broker-query",
    }
    assert all(process.exitcode == 0 for process in processes)
