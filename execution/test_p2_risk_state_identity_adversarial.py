from __future__ import annotations

from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal


class CountingExecutor(PaperExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return super().execute(request)


def _request(fingerprint: str = "a" * 64) -> ExecutionRequest:
    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=1.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        risk_state_fingerprint=fingerprint,
    )


def test_risk_identity_missing_authoritative_provider_fails_closed() -> None:
    executor = CountingExecutor()
    gateway = ExecutionGateway(executor, kill_switch=__import__("core.kill_switch", fromlist=["KillSwitch"]).KillSwitch())

    result = gateway.execute("risk-provider-missing", _request())

    assert result.status is GatewayStatus.BLOCKED
    assert "estado de risco" in result.message.lower()
    assert executor.calls == 0


def test_risk_identity_change_after_evaluation_blocks_before_executor() -> None:
    executor = CountingExecutor()
    current = {"value": "a" * 64}
    gateway = ExecutionGateway(
        executor,
        kill_switch=__import__("core.kill_switch", fromlist=["KillSwitch"]).KillSwitch(),
        risk_state_fingerprint_provider=lambda: current["value"],
    )

    first = gateway.execute("risk-identity-change", _request(), timestamp=None)
    assert first.status is GatewayStatus.ACCEPTED
    assert executor.calls == 1

    current["value"] = "b" * 64
    second = gateway.execute("risk-identity-change-2", _request())

    assert second.status is GatewayStatus.BLOCKED
    assert "estado de risco" in second.message.lower()
    assert executor.calls == 1
