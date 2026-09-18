from threading import Lock, Thread
from pathlib import Path

from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


def _contracts():
    auth = RealExecutionAuthorization("auth", "audit", "fake", "adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm",
        audit_id="audit",
        audit_verified=True,
        authorization_active=True,
        safety_ready=True,
        broker_available=True,
        broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True,
        kill_switch_clear=True,
        market_healthy=True,
        recovery_safe=True,
        risk_approved=True,
        broker_available=True,
    )
    return auth, admission, safety


def test_two_real_gateway_instances_cannot_double_dispatch(tmp_path: Path):
    class CountingAdapter:
        def __init__(self):
            self.lock = Lock()
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            with self.lock:
                self.calls += 1
            return ExecutionResult(True, "accepted", f"EXT-{self.calls}")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    path = tmp_path / "ledger.json"
    auth, admission, safety = _contracts()
    gateways = [
        RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path)),
        RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path)),
    ]
    results = []

    def run(gateway):
        results.append(
            gateway.execute(
                broker="fake",
                request_id="same-real-id",
                request=_request(),
                authorization=auth,
                admission=admission,
                safety=safety,
            )
        )

    threads = [Thread(target=run, args=(gateway,)) for gateway in gateways]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert adapter.calls == 1
    assert sorted(result.status for result in results) == sorted(
        [RealGatewayStatus.ADMITTED, RealGatewayStatus.BLOCKED]
    )


def test_real_persistence_failure_after_dispatch_never_releases_request_for_retry(tmp_path: Path, monkeypatch):
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def is_available(self):
            return True

        def execute(self, _request):
            self.calls += 1
            return ExecutionResult(True, "accepted", "EXT-FAIL")

    adapter = CountingAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    path = tmp_path / "ledger.json"
    auth, admission, safety = _contracts()
    ledger = ExecutionLedger(path)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)

    original = ledger.mark_accepted

    def fail_terminal(_request_id):
        raise OSError("terminal persistence failed")

    monkeypatch.setattr(ledger, "mark_accepted", fail_terminal)
    first = gateway.execute(
        broker="fake",
        request_id="persist-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert first.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1

    restarted = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path))
    retry = restarted.execute(
        broker="fake",
        request_id="persist-failure",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert retry.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1
    # The durable ledger remains RESERVED because the terminal write itself failed.
    assert ExecutionLedger(path).status("persist-failure").value == "RESERVED"
    assert original is not None
