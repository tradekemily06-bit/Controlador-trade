from pathlib import Path

import pytest

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def test_ledger_survives_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    first = ExecutionLedger(path)
    first.record("req-001")

    restored = ExecutionLedger(path)
    assert restored.contains("req-001") is True
    assert restored.records() == ("req-001",)


def test_gateway_rejects_duplicate_after_restart(tmp_path: Path):
    path = tmp_path / "ledger.json"
    first = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    accepted = first.execute("req-001", request())
    assert accepted.status is GatewayStatus.ACCEPTED

    restored = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    duplicate = restored.execute("req-001", request())
    assert duplicate.status is GatewayStatus.DUPLICATE


def test_rejected_execution_is_not_recorded(tmp_path: Path):
    path = tmp_path / "ledger.json"
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    invalid = ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=-1.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )
    result = gateway.execute("req-001", invalid)
    assert result.status is GatewayStatus.INVALID_REQUEST
    assert ExecutionLedger(path).records() == ()


def test_invalid_ledger_fails_closed(tmp_path: Path):
    path = tmp_path / "ledger.json"
    path.write_text('{"invalid": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="ledger de execução inválido"):
        ExecutionLedger(path)


def test_empty_request_id_is_rejected(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    with pytest.raises(ValueError, match="request_id não pode ser vazio"):
        ledger.contains(" ")

from threading import Lock, Thread
from execution.ports import ExecutionResult


def test_gateway_reserves_before_concurrent_executors(tmp_path):
    class CountingExecutor:
        def __init__(self):
            self._lock = Lock()
            self.calls = 0

        def execute(self, _request):
            with self._lock:
                self.calls += 1
            return ExecutionResult(accepted=True, message="accepted", external_id="EXT-1")

    path = tmp_path / "ledger.json"
    executor = CountingExecutor()
    first = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ExecutionLedger(path))
    second = ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path))

    # The first gateway establishes the normal persisted path.
    assert first.execute("req-concurrent", request()).status is GatewayStatus.ACCEPTED
    assert second.execute("req-concurrent", request()).status is GatewayStatus.DUPLICATE
    assert executor.calls == 0


def test_two_gateways_share_ledger_without_double_dispatch(tmp_path):
    class BlockingExecutor:
        def __init__(self):
            self._lock = Lock()
            self.calls = 0

        def execute(self, _request):
            with self._lock:
                self.calls += 1
            return ExecutionResult(accepted=True, message="accepted", external_id=f"EXT-{self.calls}")

    path = tmp_path / "ledger-race.json"
    executor = BlockingExecutor()
    gateways = [
        ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path)),
        ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path)),
    ]
    results = []

    def run(gateway):
        results.append(gateway.execute("req-race", request()).status)

    threads = [Thread(target=run, args=(gateway,)) for gateway in gateways]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results, key=lambda status: status.value) == sorted(
        [GatewayStatus.ACCEPTED, GatewayStatus.DUPLICATE], key=lambda status: status.value
    )
    assert executor.calls == 1


def test_unknown_ledger_requires_explicit_reconciliation(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-unknown")
    ledger.mark_unknown("req-unknown")

    with pytest.raises(ValueError, match="reconciliação explícita"):
        ledger.mark_accepted("req-unknown")

    with pytest.raises(ValueError, match="reconciliação explícita"):
        ledger.mark_rejected("req-unknown")

    ledger.reconcile("req-unknown", executed=True)
    assert ledger.status("req-unknown") is ExecutionLedgerStatus.RECONCILED_EXECUTED

def test_external_id_survives_restart_and_is_unique(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("req-1")
    ledger.bind_external_id("req-1", " ext-1 ")
    assert ExecutionLedger(path).external_id("req-1") == "ext-1"

    ExecutionLedger(path).reserve("req-2")
    with pytest.raises(ValueError, match="outro request_id"):
        ExecutionLedger(path).bind_external_id("req-2", "ext-1")


def test_legacy_status_only_ledger_is_backward_compatible(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('{"req-legacy":"ACCEPTED"}', encoding="utf-8")
    ledger = ExecutionLedger(path)
    assert ledger.status("req-legacy") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("req-legacy") is None


def test_duplicate_persisted_external_id_fails_closed(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(
        '{"req-1":{"status":"ACCEPTED","external_id":"ext-dup"},'
        '"req-2":{"status":"ACCEPTED","external_id":"ext-dup"}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="external_id duplicado"):
        ExecutionLedger(path)



def test_per_request_execution_lock_serializes_dispatch_and_reconciliation(tmp_path):
    from threading import Event, Thread

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    entered = Event()
    release = Event()
    order = []

    def holder():
        with ledger.request_execution_lock("same-request"):
            order.append("holder-entered")
            entered.set()
            release.wait(timeout=2)
            order.append("holder-exited")

    def waiter():
        entered.wait(timeout=2)
        with ledger.request_execution_lock("same-request"):
            order.append("waiter-entered")

    first = Thread(target=holder)
    second = Thread(target=waiter)
    first.start()
    second.start()
    assert entered.wait(timeout=2)
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert order == ["holder-entered", "holder-exited", "waiter-entered"]



def test_per_request_lock_does_not_use_raw_request_id_as_path(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    malicious = "../outside/../../request-id"

    with ledger.request_execution_lock(malicious):
        assert not (tmp_path.parent / "outside").exists()
        lock_files = list(tmp_path.glob(".*.execution.lock.lock"))
        assert len(lock_files) == 1
        assert "request-id" not in lock_files[0].name
        assert len(lock_files[0].name.split(".")) >= 4

    # The lock file is temporary and may be removed when the context exits.
    assert not (tmp_path.parent / "outside").exists()


def test_public_ledger_mutators_respect_request_execution_lock(tmp_path):
    from threading import Event, Thread

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-lock")
    entered = Event()
    release = Event()
    finished = Event()

    def mutate():
        entered.set()
        ledger.mark_unknown("req-lock")
        finished.set()

    with ledger.request_execution_lock("req-lock"):
        worker = Thread(target=mutate)
        worker.start()
        assert entered.wait(timeout=2)
        assert not finished.wait(timeout=0.2)
        release.set()

    worker.join(timeout=2)
    assert finished.is_set()
    assert ledger.status("req-lock") is ExecutionLedgerStatus.UNKNOWN


def test_request_id_with_outer_whitespace_is_rejected(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    for operation in (
        lambda: ledger.request_execution_lock(" req "),
        lambda: ledger.reserve(" req "),
        lambda: ledger.status(" req "),
    ):
        import pytest
        with pytest.raises(ValueError, match="canônico"):
            operation()


def test_ledger_rejects_noncanonical_persisted_request_id(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('{" req ": "ACCEPTED"}', encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="ledger"):
        ExecutionLedger(path)


def test_legacy_list_rejects_noncanonical_request_id(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('[" req "]', encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="ledger"):
        ExecutionLedger(path)


def test_request_execution_lock_is_reentrant_for_public_mutators(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    with ledger.request_execution_lock("nested"):
        ledger.reserve("nested")
        ledger.bind_external_id("nested", "EXT-NESTED")
        ledger.mark_accepted("nested")
    assert ledger.status("nested") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("nested") == "EXT-NESTED"
