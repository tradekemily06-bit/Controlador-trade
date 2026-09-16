from dataclasses import dataclass

from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
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
        duration_seconds=1,
        mode=mode,
    )


def ready_barrier() -> GlobalOperationalBarrier:
    return GlobalOperationalBarrier((SafetyComponent("test", True),))


def blocked_barrier() -> GlobalOperationalBarrier:
    return GlobalOperationalBarrier((SafetyComponent("test", False, "incidente ativo"),))


def test_remote_bridge_requires_global_barrier_before_health_or_dispatch():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"))
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is False
    assert "barreira operacional global" in result.message
    assert bridge.calls == 0


def test_remote_bridge_blocks_when_global_barrier_is_blocked():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"))
    result = SafeRemoteMT5Executor(bridge, blocked_barrier).execute(request())
    assert result.accepted is False
    assert "barreira operacional global" in result.message
    assert bridge.calls == 0


def test_remote_bridge_requires_healthy_demo():
    bridge = FakeBridge(BridgeHealth(False, False, "indisponível"))
    result = SafeRemoteMT5Executor(bridge, ready_barrier).execute(request())
    assert result.accepted is False
    assert bridge.calls == 0


def test_remote_bridge_never_accepts_real():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"))
    result = SafeRemoteMT5Executor(bridge, ready_barrier).execute(request(ExecutionMode.REAL))
    assert result.accepted is False
    assert bridge.calls == 0


def test_remote_bridge_executes_only_after_global_barrier_and_demo_health():
    bridge = FakeBridge(BridgeHealth(True, True, "MT5 DEMO disponível"))
    result = SafeRemoteMT5Executor(bridge, ready_barrier).execute(request())
    assert result.accepted is True
    assert result.external_id == "demo-1"
    assert bridge.calls == 1
