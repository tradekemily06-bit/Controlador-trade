from dataclasses import dataclass

from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.remote_mt5_bridge import BridgeHealth, SafeRemoteMT5Executor


@dataclass
class FakeBridge:
    health_result: BridgeHealth
    calls: int = 0
    result: object = ExecutionResult(True, "demo enviada", "demo-1")
    health_error: Exception | None = None
    execute_error: Exception | None = None

    def health(self) -> BridgeHealth:
        if self.health_error is not None:
            raise self.health_error
        return self.health_result

    def execute_demo(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls += 1
        if self.execute_error is not None:
            raise self.execute_error
        return self.result


def request(mode: ExecutionMode = ExecutionMode.DEMO) -> ExecutionRequest:
    from core.models import Signal

    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=mode,
    )


def test_remote_bridge_requires_healthy_demo():
    bridge = FakeBridge(BridgeHealth(False, False, "indisponível"))
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is False
    assert bridge.calls == 0


def test_remote_bridge_never_accepts_real():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"))
    result = SafeRemoteMT5Executor(bridge).execute(request(ExecutionMode.REAL))
    assert result.accepted is False
    assert bridge.calls == 0


def test_remote_bridge_executes_only_after_demo_health():
    bridge = FakeBridge(BridgeHealth(True, True, "MT5 DEMO disponível"))
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is True
    assert result.external_id == "demo-1"
    assert bridge.calls == 1


def test_remote_bridge_fails_closed_when_health_raises():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"), health_error=TimeoutError("secret transport detail"))
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is False
    assert "secret transport detail" not in result.message
    assert "TimeoutError" in result.message
    assert bridge.calls == 0


def test_remote_bridge_fails_closed_when_execution_raises():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"), execute_error=RuntimeError("credential leak"))
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is False
    assert "credential leak" not in result.message
    assert "RuntimeError" in result.message
    assert bridge.calls == 1


def test_remote_bridge_rejects_invalid_health_result():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"))
    bridge.health_result = "healthy"  # type: ignore[assignment]
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is False
    assert bridge.calls == 0


def test_remote_bridge_rejects_invalid_execution_result():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"), result={"accepted": True})
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is False
    assert bridge.calls == 1
