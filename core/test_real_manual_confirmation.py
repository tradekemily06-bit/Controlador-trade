from datetime import datetime, timedelta, timezone

import pytest

from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyReport
from core.p117_real_admission import RealAdmission, RealAdmissionStatus
from core.real_manual_confirmation import RealManualConfirmationGate
from execution.ports import ExecutionMode, ExecutionRequest
from execution.real_gateway import RealGatewayResult, RealGatewayStatus


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def real_request(amount=1.0):
    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=amount,
        duration_seconds=60,
        mode=ExecutionMode.REAL,
        request_id="req-real-001",
    )


class SpyGateway:
    def __init__(self):
        self.calls = 0

    def execute(self, **kwargs):
        self.calls += 1
        return RealGatewayResult(RealGatewayStatus.ADMITTED, "sent")


def valid_dependencies():
    authorization = RealExecutionAuthorization(
        authorization_id="auth-1",
        audit_id="audit-1",
        broker_id="broker-1",
        adapter_id="adapter-1",
        explicitly_enabled=True,
        real_execution_allowed=True,
    )
    admission = RealAdmission("admission-1", "audit-1", RealAdmissionStatus.ADMITTED, "broker-1", ())
    from core.p114_real_safety_gate import RealSafetyState
    safety = RealSafetyReport(RealSafetyState.READY, ())
    return authorization, admission, safety


def test_prepare_never_calls_gateway():
    gate = RealManualConfirmationGate()
    confirmation = gate.prepare(request=real_request(), now=NOW)
    assert confirmation.request_id == "req-real-001"


def test_prepare_is_bound_to_exact_request():
    gate = RealManualConfirmationGate()
    confirmation = gate.prepare(request=real_request(), now=NOW)
    spy = SpyGateway()
    authorization, admission, safety = valid_dependencies()
    with pytest.raises(ValueError, match="não corresponde"):
        gate.confirm(
            confirmation_id=confirmation.confirmation_id,
            request=real_request(amount=2.0),
            broker="broker-1",
            authorization=authorization,
            admission=admission,
            safety=safety,
            gateway=spy,
            now=NOW,
        )
    assert spy.calls == 0


def test_confirmation_is_single_use():
    gate = RealManualConfirmationGate()
    confirmation = gate.prepare(request=real_request(), now=NOW)
    spy = SpyGateway()
    authorization, admission, safety = valid_dependencies()
    gate.confirm(
        confirmation_id=confirmation.confirmation_id,
        request=real_request(),
        broker="broker-1",
        authorization=authorization,
        admission=admission,
        safety=safety,
        gateway=spy,
        now=NOW,
    )
    with pytest.raises(ValueError, match="já consumida"):
        gate.confirm(
            confirmation_id=confirmation.confirmation_id,
            request=real_request(),
            broker="broker-1",
            authorization=authorization,
            admission=admission,
            safety=safety,
            gateway=spy,
            now=NOW,
        )
    assert spy.calls == 1


def test_expired_confirmation_never_reaches_gateway():
    gate = RealManualConfirmationGate(ttl_seconds=10)
    confirmation = gate.prepare(request=real_request(), now=NOW)
    spy = SpyGateway()
    authorization, admission, safety = valid_dependencies()
    with pytest.raises(ValueError, match="expirada"):
        gate.confirm(
            confirmation_id=confirmation.confirmation_id,
            request=real_request(),
            broker="broker-1",
            authorization=authorization,
            admission=admission,
            safety=safety,
            gateway=spy,
            now=NOW + timedelta(seconds=11),
        )
    assert spy.calls == 0


class FakeAdapter:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        from execution.ports import ExecutionResult
        self.calls += 1
        return ExecutionResult(True, "real fake accepted", "external-001")


def test_valid_confirmation_reaches_real_gateway_only_once(tmp_path):
    from execution.broker_registry import BrokerRegistry
    from execution.adapter_gateway import BrokerAdapterGateway
    from execution.execution_ledger import ExecutionLedger
    from execution.real_gateway import RealExecutionGateway

    adapter = FakeAdapter()
    registry = BrokerRegistry()
    registry.register("broker-1", adapter)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "real-ledger.json"),
    )
    gate = RealManualConfirmationGate()
    confirmation = gate.prepare(request=real_request(), now=NOW)
    authorization, admission, safety = valid_dependencies()

    result = gate.confirm(
        confirmation_id=confirmation.confirmation_id,
        request=real_request(),
        broker="broker-1",
        authorization=authorization,
        admission=admission,
        safety=safety,
        gateway=gateway,
        now=NOW,
    )

    assert result.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1
