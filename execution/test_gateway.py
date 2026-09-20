from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleStore
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
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), allow_ephemeral=True)

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.ACCEPTED
    assert result.execution is not None
    assert result.execution.external_id == "PAPER-000001"


def test_gateway_blocks_active_kill_switch_before_executor():
    executor = PaperExecutor()
    kill_switch = KillSwitch()
    kill_switch.activate("emergência")
    gateway = ExecutionGateway(executor, kill_switch, allow_ephemeral=True)

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.BLOCKED
    assert executor.executions() == ()


def test_gateway_rejects_real_mode_in_p5():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), allow_ephemeral=True)

    result = gateway.execute("req-1", request(mode=ExecutionMode.REAL))

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_rejects_wait_signal():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), allow_ephemeral=True)

    result = gateway.execute("req-1", request(signal=Signal.AGUARDAR))

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_rejects_duplicate_request_id():
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch(), allow_ephemeral=True)

    first = gateway.execute("req-1", request())
    second = gateway.execute("req-1", request())

    assert first.status is GatewayStatus.ACCEPTED
    assert second.status is GatewayStatus.DUPLICATE
    assert len(executor.executions()) == 1


def test_gateway_does_not_mark_invalid_request_as_processed():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), allow_ephemeral=True)

    invalid = gateway.execute("req-1", request(mode=ExecutionMode.REAL))
    valid = gateway.execute("req-1", request())

    assert invalid.status is GatewayStatus.INVALID_REQUEST
    assert valid.status is GatewayStatus.ACCEPTED


def test_gateway_rejects_empty_request_id():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), allow_ephemeral=True)

    result = gateway.execute("   ", request())

    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_fails_closed_when_executor_raises():
    class BrokenExecutor:
        def execute(self, _request):
            raise RuntimeError("falha simulada")

    gateway = ExecutionGateway(BrokenExecutor(), KillSwitch(), allow_ephemeral=True)

    result = gateway.execute("req-1", request())
    retry = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert retry.status is GatewayStatus.EXECUTOR_ERROR


def test_gateway_rejects_invalid_executor_result():
    class InvalidExecutor:
        def execute(self, _request):
            return "not-an-execution-result"

    gateway = ExecutionGateway(InvalidExecutor(), KillSwitch(), allow_ephemeral=True)

    result = gateway.execute("req-1", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR


def test_gateway_requires_executor():
    try:
        ExecutionGateway(None, KillSwitch(), allow_ephemeral=True)
    except ValueError as exc:
        assert "executor" in str(exc)
    else:
        raise AssertionError("gateway deveria exigir executor")


def test_executor_rejection_is_not_reported_as_accepted():
    class RejectingExecutor:
        def execute(self, _request):
            return ExecutionResult(accepted=False, message="rejeitado")

    gateway = ExecutionGateway(RejectingExecutor(), KillSwitch(), allow_ephemeral=True)

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
    result = ExecutionGateway(executor, KillSwitch(), allow_ephemeral=True).execute("req-bound", request())
    assert result.status is GatewayStatus.ACCEPTED
    assert executor.request.request_id == "req-bound"


def test_gateway_rejects_conflicting_internal_request_id():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), allow_ephemeral=True)
    conflicting = ExecutionRequest("BTCUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.DEMO, request_id="req-inner")
    result = gateway.execute("req-outer", conflicting)
    assert result.status is GatewayStatus.INVALID_REQUEST
    assert "difere" in result.message


def test_gateway_rejects_non_finite_amount():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), allow_ephemeral=True)
    invalid = ExecutionRequest("BTCUSD", Signal.COMPRA, float("nan"), 60, ExecutionMode.DEMO)
    result = gateway.execute("req-nan", invalid)
    assert result.status is GatewayStatus.INVALID_REQUEST


def test_gateway_with_ledger_reserves_before_dispatch_and_marks_acceptance(tmp_path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch(), ledger=ledger, lifecycle=ExecutionLifecycleStore(tmp_path / "lifecycle.json"))
    result = gateway.execute("req-ledger", request())
    assert result.status is GatewayStatus.ACCEPTED
    assert ledger.status("req-ledger") is ExecutionLedgerStatus.ACCEPTED


def test_gateway_with_ledger_persists_unknown_after_executor_exception(tmp_path):
    class BrokenExecutor:
        def execute(self, _request):
            raise RuntimeError("falha depois da entrada no executor")

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = ExecutionGateway(BrokenExecutor(), KillSwitch(), ledger=ledger, lifecycle=ExecutionLifecycleStore(tmp_path / "lifecycle.json"))
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


def test_gateway_durably_binds_external_id_before_terminal_acceptance(tmp_path):
    class ExternalExecutor:
        def execute(self, _request):
            return ExecutionResult(True, "accepted", "BROKER-42")

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = ExecutionGateway(ExternalExecutor(), KillSwitch(), ledger=ledger, lifecycle=ExecutionLifecycleStore(tmp_path / "lifecycle.json"))

    result = gateway.execute("req-external", request())

    assert result.status is GatewayStatus.ACCEPTED
    assert ledger.external_id("req-external") == "BROKER-42"

def test_gateway_does_not_downgrade_durable_acceptance_when_lifecycle_persist_fails(tmp_path):
    from execution.execution_lifecycle import ExecutionLifecycleStore, ExecutionLifecycleState

    class FailingLifecycle(ExecutionLifecycleStore):
        def put(self, record):
            if record.state is ExecutionLifecycleState.ACCEPTED:
                raise OSError("falha de persistência do lifecycle")
            return super().put(record)

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = FailingLifecycle(tmp_path / "lifecycle.json")
    gateway = ExecutionGateway(
        PaperExecutor(),
        KillSwitch(),
        ledger=ledger,
        lifecycle=lifecycle,
    )

    result = gateway.execute("req-lifecycle-crash", request())

    assert result.status is GatewayStatus.EXECUTOR_ERROR
    assert ledger.status("req-lifecycle-crash") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("req-lifecycle-crash") == "PAPER-000001"
    assert lifecycle.get("req-lifecycle-crash").state is ExecutionLifecycleState.PENDING



def test_gateway_requires_durable_state_by_default():
    try:
        ExecutionGateway(PaperExecutor(), KillSwitch())
    except ValueError as exc:
        assert "estado durável" in str(exc)
    else:
        raise AssertionError("gateway de produção não pode operar sem Ledger + Lifecycle")



def test_execution_result_rejects_accepted_and_ambiguous_combination():
    try:
        ExecutionResult(True, "contraditório", "EXT-1", ambiguous=True)
    except ValueError as exc:
        assert "aceito e ambíguo" in str(exc)
    else:
        raise AssertionError("resultado aceito+ambíguo deveria ser impossível")


