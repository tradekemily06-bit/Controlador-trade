from core.models import Signal
from execution.gateway import ExecutionGateway
from execution.paper import PaperExecutor
from core.kill_switch import KillSwitch
from execution.ports import ExecutionMode, ExecutionRequest


def test_legacy_gateway_rejects_real_before_executor() -> None:
    executor = PaperExecutor()
    gateway = ExecutionGateway(executor, KillSwitch())
    request = ExecutionRequest(
        mode=ExecutionMode.REAL,
        signal=Signal.COMPRA,
        symbol="EURUSD",
        amount=1.0,
        duration_seconds=60,
    )

    result = gateway.execute("legacy-real-block", request)

    assert result.status.value == "INVALID_REQUEST"
    assert executor.executions() == ()
