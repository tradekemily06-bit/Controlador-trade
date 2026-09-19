from dataclasses import dataclass

from core.models import Signal\nfrom execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
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
        duration_seconds=60,
        mode=mode,
        request_id="remote-1",
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


def test_remote_bridge_rejects_non_boolean_health_flags():
    bridge = FakeBridge(BridgeHealth("yes", True, "ok"))
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is False
    assert "flags de health inválidas" in result.message
    assert bridge.calls == 0


def test_remote_bridge_rejects_malformed_execution_result():
    @dataclass
    class MalformedBridge(FakeBridge):
        def execute_demo(self, request: ExecutionRequest) -> ExecutionResult:
            self.calls += 1
            return ExecutionResult("yes", "demo enviada", "demo-1")

    bridge = MalformedBridge(BridgeHealth(True, True, "ok"))
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is False
    assert "accepted inválido" in result.message
    assert bridge.calls == 1


def test_remote_bridge_rejects_request_subclass_before_health():
    from core.models import Signal

    class RequestOverride(ExecutionRequest):
        pass

    bridge = FakeBridge(BridgeHealth(True, True, "ok"))
    forged = RequestOverride("EURUSD", Signal.COMPRA, 0.01, 60, ExecutionMode.DEMO, "remote-1")
    result = SafeRemoteMT5Executor(bridge).execute(forged)
    assert result.accepted is False
    assert bridge.calls == 0


def test_remote_bridge_converts_health_exception_to_rejection():
    class BrokenBridge(FakeBridge):
        def health(self) -> BridgeHealth:
            raise RuntimeError("health down")

    bridge = BrokenBridge(BridgeHealth(True, True, "ok"))
    result = SafeRemoteMT5Executor(bridge).execute(request())
    assert result.accepted is False
    assert bridge.calls == 0


def test_remote_bridge_rejects_noncanonical_request_id_before_health():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"))
    forged = request()
    forged = ExecutionRequest(
        forged.symbol,
        forged.signal,
        forged.amount,
        forged.duration_seconds,
        forged.mode,
        " remote-1 ",
    )
    result = SafeRemoteMT5Executor(bridge).execute(forged)

    assert result.accepted is False
    assert "request_id" in result.message
    assert bridge.calls == 0


def test_remote_bridge_rejects_nonfinite_amount_before_health():
    bridge = FakeBridge(BridgeHealth(True, True, "ok"))
    forged = ExecutionRequest(
        "EURUSD",
        Signal.COMPRA,
        float("nan"),
        60,
        ExecutionMode.DEMO,
        "remote-nan",
    )
    result = SafeRemoteMT5Executor(bridge).execute(forged)

    assert result.accepted is False
    assert "amount" in result.message
    assert bridge.calls == 0
