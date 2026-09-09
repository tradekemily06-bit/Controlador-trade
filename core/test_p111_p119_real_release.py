from core.models import Signal
from core.p111_pre_real_audit import PreRealAuditBoundary, PreRealAuditStatus
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyState
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary, ReleaseAuditStatus
from core.p117_real_admission import RealAdmissionBoundary, RealAdmissionStatus
from core.p118_real_monitoring import RealMonitoringBoundary, RealOutcomeStatus
from core.p119_release_closure import RealReleaseClosureBoundary, RealReleaseState
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class FakeAdapter:
    def __init__(self, available=True):
        self.available = available
        self.calls = 0

    def is_available(self):
        return self.available

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "fake real execution accepted", "external-1")


def test_p111_p116_p117_p119_positive_flow():
    p111 = PreRealAuditBoundary().audit(
        audit_id="a111", p110_decision="VALIDATED", safety_verified=True,
        risk_verified=True, gateway_present=True, broker_boundary_present=True,
    )
    assert p111.status is PreRealAuditStatus.VERIFIED

    auth = RealExecutionAuthorization("auth", "a111", "fake", "fake-adapter", True, True)
    safety = RealSafetyGate().evaluate(
        authorization_active=auth.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    assert safety.state is RealSafetyState.READY

    shadow = ShadowValidationBoundary().validate(
        validation_id="shadow", adapter_available=True, real_safety_ready=True,
        duplicate_blocked=True, kill_switch_blocked=True,
        real_mode_rejected_by_shadow=True,
    )
    assert shadow.passed

    p116 = RealReleaseAuditBoundary().audit(
        audit_id="a116", pre_real_verified=p111.verified,
        shadow_passed=shadow.passed, safety_ready=safety.ready,
        broker_boundary_ready=True, explicit_real_contract=True,
    )
    assert p116.status is ReleaseAuditStatus.VERIFIED

    p117 = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="a116", audit_verified=p116.verified,
        authorization_active=auth.active, safety_ready=safety.ready,
        broker_available=True, broker_id="fake",
    )
    assert p117.status is RealAdmissionStatus.ADMITTED

    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry))
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)
    result = gateway.execute(broker="fake", request=request, authorization=auth, admission=p117, safety=safety)
    assert result.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1

    observation = RealMonitoringBoundary().observe(
        observation_id="obs", request_id="req", result=result.execution,
    )
    assert observation.status is RealOutcomeStatus.ACCEPTED

    p119 = RealReleaseClosureBoundary().close(
        release_id="release", p116_verified=p116.verified,
        p117_admitted=p117.admitted, p118_available=True,
        multi_broker_boundary=True,
    )
    assert p119.state is RealReleaseState.RELEASED


def test_real_authorization_is_explicit():
    try:
        RealExecutionAuthorization("a", "audit", "broker", "adapter", False, True)
    except ValueError:
        pass
    else:
        raise AssertionError("REAL must require explicit enablement")


def test_real_safety_fails_closed():
    report = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=False,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    assert report.state is RealSafetyState.BLOCKED


def test_real_gateway_blocks_without_active_authorization():
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry))
    auth = RealExecutionAuthorization("a", "audit", "fake", "adapter", False, False)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=False,
        authorization_active=False, safety_ready=False,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=False, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)
    result = gateway.execute(broker="fake", request=request, authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
