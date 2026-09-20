from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
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


def test_gateway_binds_missing_internal_request_id_to_external_identity():
    class CapturingExecutor:
        def __init__(self): self.request = None
        def execute(self, request):
            self.request = request
            return ExecutionResult(True, "ok", "EXT-1")
    executor = CapturingExecutor()
    result = ExecutionGateway(executor, KillSwitch()).execute("req-bound", request())
    assert result.status is GatewayStatus.ACCEPTED
    assert executor.request.request_id == "req-bound"


def test_gateway_rejects_conflicting_internal_request_id():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())
    conflicting = ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.DEMO, request_id="req-inner")
    result = gateway.execute("req-outer", conflicting)
    assert result.status is GatewayStatus.INVALID_REQUEST
    assert "difere" in result.message


def test_gateway_rejects_non_finite_amount():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())
    invalid = ExecutionRequest("BTCUSD", Signal.COMPRA, float("nan"), 60, ExecutionMode.DEMO)
    result = gateway.execute("req-nan", invalid)
    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_with_ledger_reserves_before_dispatch_and_marks_acceptance(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ledger)
    result = gateway.execute("req-ledger", request())
    assert result.status is GatewayStatus.ACCEPTED
    assert ledger.status("req-ledger") is ExecutionLedgerStatus.ACCEPTED


def test_gateway_with_ledger_persists_unknown_after_executor_exception(tmp_path):
    class BrokenExecutor:
        def execute(self, _request):
            raise RuntimeError("falha depois da entrada no executor")

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = ExecutionGateway(BrokenExecutor(), KillSwitch(), ledger=ledger)
    result = gateway.execute("req-unknown", request())
    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ledger.status("req-unknown") is ExecutionLedgerStatus.UNKNOWN
    retry = gateway.execute("req-unknown", request())
    assert retry.status is GatewayStatus.DUPLICATE


def test_gateway_persists_ambiguous_result_as_unknown(tmp_path):
    class AmbiguousExecutor:
        def execute(self, _request):
            return ExecutionResult(
                accepted=False,
                message="parcial; reconciliação necessária",
                external_id="EXT-PARTIAL",
                ambiguous=True,
            )

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    from execution.execution_lifecycle import ExecutionLifecycleStore, ExecutionLifecycleState

    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = ExecutionGateway(
        AmbiguousExecutor(),
        KillSwitch(),
        ledger=ledger,
        lifecycle=lifecycle,
    )

    result = gateway.execute("req-partial", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert result.execution.ambiguous is True
    assert ledger.status("req-partial") is ExecutionLedgerStatus.UNKNOWN
    assert lifecycle.get("req-partial").state is ExecutionLifecycleState.UNKNOWN
