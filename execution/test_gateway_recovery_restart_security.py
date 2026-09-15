from pathlib import Path

from core.kill_switch import KillSwitch
from core.models import Signal
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest


def _request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="TEST",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def test_reserved_request_remains_blocked_after_restart_until_reconciled(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("restart-reserved")

    executor = PaperExecutor()
    restarted = ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path))

    result = restarted.execute("restart-reserved", _request())

    assert result.status is GatewayStatus.BLOCKED
    assert "estado incerto" in result.message
    assert executor.executions() == ()
    assert ExecutionLedger(path).status("restart-reserved") is ExecutionLedgerStatus.RESERVED


def test_reconciliation_is_terminal_for_original_request_and_never_replays(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ledger = ExecutionLedger(path)
    ledger.reserve("reconciled-request")
    ledger.mark_unknown("reconciled-request")
    ledger.reconcile("reconciled-request", executed=False)

    executor = PaperExecutor()
    restarted = ExecutionGateway(executor, KillSwitch(), ledger=ExecutionLedger(path))
    result = restarted.execute("reconciled-request", _request())

    assert result.status is GatewayStatus.DUPLICATE
    assert executor.executions() == ()
    assert ExecutionLedger(path).status("reconciled-request") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
