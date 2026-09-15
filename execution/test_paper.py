from concurrent.futures import ThreadPoolExecutor

from core.models import Signal
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest
from execution.reconciliation import Reconciler


def make_request(
    *,
    mode: ExecutionMode = ExecutionMode.DEMO,
    amount: float = 10.0,
    duration_seconds: int = 60,
) -> ExecutionRequest:
    return ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=amount,
        duration_seconds=duration_seconds,
        mode=mode,
    )


def test_paper_executor_accepts_demo_execution():
    executor = PaperExecutor()

    result = executor.execute(make_request())

    assert result.accepted is True
    assert result.external_id == "PAPER-000001"
    assert len(executor.executions()) == 1


def test_paper_executor_rejects_real_mode():
    executor = PaperExecutor()

    result = executor.execute(
        make_request(mode=ExecutionMode.REAL)
    )

    assert result.accepted is False
    assert executor.executions() == ()


def test_paper_executor_rejects_invalid_amount():
    executor = PaperExecutor()

    result = executor.execute(make_request(amount=0))

    assert result.accepted is False
    assert executor.executions() == ()


def test_paper_executor_rejects_invalid_duration():
    executor = PaperExecutor()

    result = executor.execute(make_request(duration_seconds=0))

    assert result.accepted is False
    assert executor.executions() == ()


def test_paper_executor_generates_unique_ids():
    executor = PaperExecutor()

    first = executor.execute(make_request())
    second = executor.execute(make_request())

    assert first.external_id != second.external_id
    assert second.external_id == "PAPER-000002"


def test_paper_executor_generates_unique_ids_under_concurrency():
    executor = PaperExecutor()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: executor.execute(make_request()), range(40)))

    ids = [result.external_id for result in results]
    assert all(result.accepted for result in results)
    assert len(ids) == len(set(ids)) == 40
    assert {item.result.external_id for item in executor.executions()} == set(ids)


def test_reconciler_reports_consistent_execution_history():
    executor = PaperExecutor()

    executor.execute(make_request())
    executor.execute(make_request())

    result = Reconciler().reconcile(executor.executions())

    assert result.total == 2
    assert result.accepted == 2
    assert result.rejected == 0
    assert result.consistent is True


def test_reconciler_handles_empty_history():
    result = Reconciler().reconcile(())

    assert result.total == 0
    assert result.accepted == 0
    assert result.rejected == 0
    assert result.consistent is True
