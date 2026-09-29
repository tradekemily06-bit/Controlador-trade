from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


def request(signal=Signal.COMPRA, mode=ExecutionMode.DEMO):
    return ExecutionRequest(
        symbol="BTCUSD",
        signal=signal,
        amount=10.0,
        duration_seconds=60,
        mode=mode,
    )


def test_gateway_executes_valid_demo_request():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.ACCEPTED
    assert result.execution is not None
    assert result.execution.external_id == "PAPER-000001"


def test_gateway_blocks_active_kill_switch_before_executor():
    executor = PaperExecutor()
    kill_switch = KillSwitch()
    kill_switch.activate("emergência")
    gateway = ExecutionGateway(executor, kill_switch)

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.BLOCKED
    assert executor.executions() == ()


def test_gateway_rejects_real_mode_in_p5():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    result = gateway.execute("req-1", request(mode=ExecutionMode.REAL))

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_rejects_wait_signal():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    result = gateway.execute("req-1", request(signal=Signal.AGUARDAR))

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_rejects_duplicate_request_id():
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch())

    first = gateway.execute("req-1", request())
    second = gateway.execute("req-1", request())

    assert first.status is GatewayStatus.ACCEPTED
    assert second.status is GatewayStatus.DUPLICATE
    assert len(executor.executions()) == 1


def test_gateway_does_not_mark_invalid_request_as_processed():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    invalid = gateway.execute("req-1", request(mode=ExecutionMode.REAL))
    valid = gateway.execute("req-1", request())

    assert invalid.status is GatewayStatus.INVALID_REQUEST
    assert valid.status is GatewayStatus.ACCEPTED


def test_gateway_rejects_empty_request_id():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())

    result = gateway.execute("   ", request())

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_fails_closed_when_executor_raises():
    class BrokenExecutor:
        def execute(self, _request):
            raise RuntimeError("falha simulada")

    gateway = ExecutionGateway(BrokenExecutor(), KillSwitch())

    result = gateway.execute("req-1", request())
    retry = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert retry.status is GatewayStatus.EXECUTOR_ERROR


def test_gateway_rejects_invalid_executor_result():
    class InvalidExecutor:
        def execute(self, _request):
            return "not-an-execution-result"

    gateway = ExecutionGateway(InvalidExecutor(), KillSwitch())

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR


def test_gateway_requires_executor():
    try:
        ExecutionGateway(None, KillSwitch())
    except ValueError as exc:
        assert "executor" in str(exc)
    else:
        raise AssertionError("gateway deveria exigir executor")


def test_executor_rejection_is_not_reported_as_accepted():
    class RejectingExecutor:
        def execute(self, _request):
            return ExecutionResult(accepted=False, message="rejeitado")

    gateway = ExecutionGateway(RejectingExecutor(), KillSwitch())

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.EXECUTION_REJECTED
    assert not result.accepted


def test_gateway_persists_reservation_before_dispatch(tmp_path):
    from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus

    class InspectingExecutor:
        def __init__(self, ledger):
            self.ledger = ledger
            self.observed = None

        def execute(self, _request):
            self.observed = self.ledger.status("req-reserved")
            return ExecutionResult(True, "accepted", "EXT-RESERVED")

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    executor = InspectingExecutor(ledger)
    gateway = ExecutionGateway(executor, KillSwitch(), ledger=ledger)

    result = gateway.execute("req-reserved", request())

    assert result.status is GatewayStatus.ACCEPTED
    assert executor.observed is ExecutionLedgerStatus.RESERVED
    assert ledger.status("req-reserved") is ExecutionLedgerStatus.ACCEPTED


def test_gateway_persisted_reservation_blocks_replay_after_restart(tmp_path):
    from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus

    ledger_path = tmp_path / "ledger.json"
    first_ledger = ExecutionLedger(ledger_path)

    class CrashingExecutor:
        def execute(self, _request):
            raise RuntimeError("broker call became uncertain")

    first = ExecutionGateway(CrashingExecutor(), KillSwitch(), ledger=first_ledger)
    result = first.execute("req-crash", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert first_ledger.status("req-crash") is ExecutionLedgerStatus.UNKNOWN

    second_ledger = ExecutionLedger(ledger_path)
    second = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=second_ledger)
    replay = second.execute("req-crash", request())

    assert replay.status is GatewayStatus.DUPLICATE
    assert second_ledger.status("req-crash") is ExecutionLedgerStatus.UNKNOWN


def test_gateway_treats_uncertain_executor_result_as_unknown(tmp_path):
    from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus

    class UncertainExecutor:
        def execute(self, _request):
            return ExecutionResult(
                accepted=False,
                message="broker aceitou, mas identidade não foi confirmada",
                uncertain=True,
            )

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = ExecutionGateway(UncertainExecutor(), KillSwitch(), ledger=ledger)

    result = gateway.execute("req-uncertain", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert result.execution is not None
    assert result.execution.uncertain is True
    assert ledger.status("req-uncertain") is ExecutionLedgerStatus.UNKNOWN


def test_gateway_rejects_inconsistent_accepted_uncertain_result(tmp_path):
    from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus

    class InconsistentExecutor:
        def execute(self, _request):
            return ExecutionResult(
                accepted=True,
                message="accepted sem certeza",
                external_id="EXT-AMBIGUOUS",
                uncertain=True,
            )

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = ExecutionGateway(InconsistentExecutor(), KillSwitch(), ledger=ledger)

    result = gateway.execute("req-inconsistent", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ledger.status("req-inconsistent") is ExecutionLedgerStatus.UNKNOWN


def test_operational_gateway_treats_accepted_without_external_id_as_unknown(tmp_path):
    from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
    from execution.execution_lifecycle import ExecutionLifecycleStore, ExecutionLifecycleState

    class MissingExternalIdExecutor:
        def execute(self, _request):
            return ExecutionResult(True, "accepted but no external id", None)

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")

    # Legacy gateway without lineage remains compatible; the operational runtime
    # supplies lineage and therefore activates the stricter external-identity rule.
    from core.operation_lineage import OperationLineageStore
    from core.operation_context_store import OperationContextStore
    from core.decision_snapshot import DecisionSnapshot
    lineage = OperationLineageStore(tmp_path / "lineage.json")
    context = OperationContextStore(tmp_path / "context.json")
    gateway = ExecutionGateway(
        MissingExternalIdExecutor(),
        KillSwitch(),
        ledger=ledger,
        lifecycle=lifecycle,
        lineage=lineage,
        operation_context=context,
    )
    snapshot = DecisionSnapshot(
        signal="COMPRA", analysis_score=80, confirmed=True, quality_score=80,
        quality_level="HIGH", actionable=True, decision="EXECUTAR",
        decision_reason="test", market_context=None, market_direction=None,
        market_score=None, operational_state_available=True, trades_today=0,
        consecutive_losses=0, symbol="EURUSD", timeframe="5m",
        decision_id="d1", cycle_id="c1", request_id="req-no-external",
    )
    result = gateway.execute("req-no-external", request(), snapshot=snapshot)

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ledger.status("req-no-external") is ExecutionLedgerStatus.UNKNOWN
    assert lifecycle.get("req-no-external").state is ExecutionLifecycleState.UNKNOWN
