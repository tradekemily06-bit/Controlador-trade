from dataclasses import dataclass

from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.remote_mt5_bridge import BridgeHealth, SafeRemoteMT5Executor


@dataclass
class FakeBridge:
    health_result: BridgeHealth
    calls: int = 0

    def health(self) -> BridgeHealth:
        return self.health_result

    def execute_demo(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls += 1
        return ExecutionResult(True, "demo enviada", "demo-1")


def request(mode: ExecutionMode = ExecutionMode.DEMO) -> ExecutionRequest:
    from core.models import Signal

    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=0,
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
