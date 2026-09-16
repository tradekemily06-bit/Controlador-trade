from core.ecosystem_incidents import EcosystemIncidentManager
from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


class CountingExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "ok", external_id="demo-1")


def _request():
    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=10.0,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
    )


def test_active_technical_incident_blocks_before_executor_dispatch():
    executor = CountingExecutor()
    incidents = EcosystemIncidentManager()
    incidents.open_incident(
        incident_id="incident-gateway-1",
        title="Falha técnica",
        message="Dados de execução indisponíveis.",
    )
    gateway = ExecutionGateway(executor, KillSwitch(), incident_manager=incidents)

    result = gateway.execute("request-incident-1", _request())

    assert result.status is GatewayStatus.BLOCKED
    assert executor.calls == 0


def test_executor_failure_opens_incident_and_blocks_following_order():
    class FailingExecutor:
        def __init__(self):
            self.calls = 0

        def execute(self, request):
            self.calls += 1
            raise RuntimeError("terminal unavailable")

    executor = FailingExecutor()
    incidents = EcosystemIncidentManager()
    gateway = ExecutionGateway(executor, KillSwitch(), incident_manager=incidents)

    first = gateway.execute("request-incident-2", _request())
    second = gateway.execute("request-incident-3", _request())

    assert first.status is GatewayStatus.EXECUTOR_ERROR
    assert second.status is GatewayStatus.BLOCKED
    assert executor.calls == 1
    assert incidents.execution_blocked() is True
