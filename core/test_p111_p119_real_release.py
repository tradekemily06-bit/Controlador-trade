from pathlib import Path

import pytest

from core.models import Signal
from core.kill_switch import KillSwitch
from core.p111_pre_real_audit import PreRealAuditBoundary, PreRealAuditStatus
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyState
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary, ReleaseAuditStatus
from core.p117_real_admission import RealAdmissionBoundary, RealAdmissionStatus
from core.p118_real_monitoring import RealMonitoringBoundary, RealOutcomeStatus
from core.p119_release_closure import RealReleaseClosureBoundary, RealReleaseState
from core.p121_external_order_reconciliation import (
    ExternalOrderObservation,
    ExternalOrderReconciliationBoundary,
    ExternalOrderStatus,
)
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class FakeAdapter:
    supports_real_execution = True
    adapter_id = "fake-adapter"

    def __init__(self, available=True, observation=None):
        self.available = available
        self.calls = 0
        self.observation = observation
        self.query_calls = 0

    def is_available(self):
        return self.available

    def query_order_by_request_id(self, request_id):
        if self.observation is None:
            raise ValueError("unexpected request_id")
        return self.observation

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "fake real execution accepted", "external-1")

    def query_order(self, external_id):
        self.query_calls += 1
        if self.observation is None or external_id != self.observation.external_id:
            raise ValueError("unexpected external_id")
        return self.observation


class NoExternalIdAdapter:
    supports_real_execution = True
    adapter_id = "fake-adapter"

    def query_order_by_request_id(self, request_id):
        raise ValueError("no broker evidence")

    def query_order(self, external_id):
        raise ValueError("no broker evidence")

    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(True, "accepted but reference missing", None)


class     def query_order(self, external_id):
        raise ValueError("no broker evidence")

:
    supports_real_execution = True
    adapter_id = "fake-adapter"

    def query_order_by_request_id(self, request_id):
        raise ValueError("no broker evidence")

    def is_available(self):
        return True

    def execute(self, request):
        raise TimeoutError("timeout after dispatch")


class QueryPort:
    adapter_id = "fake-adapter"
    def __init__(self, observation):
        self.observation = observation
        self.calls = 0

    def query_order(self, external_id):
        self.calls += 1
        if external_id != self.observation.external_id:
            raise ValueError("unexpected external_id")
        return self.observation


def _authorization():
    return RealExecutionAuthorization("auth", "a111", "fake", "fake-adapter", True, True)


def _admission(auth):
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id=auth.audit_id, audit_verified=True,
        authorization_active=auth.active, safety_ready=True,
        broker_available=True, broker_id="fake",
    )


def _safety(auth):
    return RealSafetyGate().evaluate(
        authorization_active=auth.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="req")


def test_p111_p116_p117_p119_positive_flow(tmp_path: Path):
    p111 = PreRealAuditBoundary().audit(
        audit_id="a111", p110_decision="VALIDATED", safety_verified=True,
        risk_verified=True, gateway_present=True, broker_boundary_present=True,
    )
    assert p111.status is PreRealAuditStatus.VERIFIED
    auth = _authorization()
    safety = _safety(auth)
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
    p117 = _admission(auth)
    assert p117.status is RealAdmissionStatus.ADMITTED
    registry = BrokerRegistry()
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "external-2", ExternalOrderStatus.EXECUTED, "broker confirmed"
        )
    )
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "real-ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    result = gateway.execute(broker="fake", request_id="req", request=ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="req"), authorization=auth, admission=p117, safety=safety)
    assert result.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1
    assert ledger.status("req") is ExecutionLedgerStatus.ACCEPTED
    observation = RealMonitoringBoundary().observe(observation_id="obs", request_id="req", result=result.execution)
    assert observation.status is RealOutcomeStatus.ACCEPTED
    p119 = RealReleaseClosureBoundary().close(
        release_id="release", p116_verified=p116.verified, p117_admitted=p117.admitted,
        p118_available=True, multi_broker_boundary=True,
    )
    assert p119.state is RealReleaseState.RELEASED


def test_real_authorization_is_explicit():
    try:
        RealExecutionAuthorization("a", "audit", "broker", "adapter", False, True)
    except ValueError:
        pass
    else:
        raise AssertionError("REAL must require explicit enablement")


def test_real_gateway_rechecks_live_kill_switch_before_dispatch(tmp_path: Path):
    adapter = FakeAdapter()
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    kill_switch = KillSwitch()
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
        kill_switch=kill_switch,
    )

    kill_switch.activate("emergency stop after safety snapshot")
    result = gateway.execute(
        broker="fake", request_id="kill-live",
        request=ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="kill-live"),
        authorization=auth, admission=admission, safety=safety,
    )

    assert result.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_safety_fails_closed():
    report = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=False,
        market_healthy=True, recovery_safe=True, risk_approved=True, broker_available=True,
    )
    assert report.state is RealSafetyState.BLOCKED


def test_real_gateway_blocks_without_active_authorization(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"))
    auth = RealExecutionAuthorization("a", "audit", "fake", "adapter", False, False)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=False,
        authorization_active=False, safety_ready=False, broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=False, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True, broker_available=True,
    )
    result = gateway.execute(broker="fake", request_id="blocked", request=ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="blocked"), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_unknown_without_external_id_cannot_be_locally_closed(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="unknown-1", request=ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="unknown-1"), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("unknown-1") is ExecutionLedgerStatus.UNKNOWN
    with pytest.raises(ValueError):
        gateway.reconcile_unknown(
            "unknown-1",
            broker="fake",
            authorization=_authorization(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )


def test_real_unknown_with_durable_external_id_can_be_reconciled_from_broker_query(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "external-2", ExternalOrderStatus.EXECUTED, "broker confirmed"
        )
    )
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)

    ledger.reserve("unknown-2")
    ledger.attach_external_id("unknown-2", "external-2")
    ledger.mark_unknown("unknown-2")

    auth = _authorization()
    gateway.reconcile_unknown(
        "unknown-2",
        broker="fake",
        authorization=auth,
        reconciliation_boundary=ExternalOrderReconciliationBoundary(),
    )
    assert adapter.query_calls == 1
    assert ledger.status("unknown-2") is ExecutionLedgerStatus.RECONCILED_EXECUTED


def test_real_reserved_after_restart_without_external_id_stays_unresolved(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ExecutionLedger(path).reserve("crashed")
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="crashed", request=ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="crashed"), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 0
    with pytest.raises(ValueError):
        gateway.reconcile_unknown(
            "crashed",
            broker="fake",
            authorization=_authorization(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )


def test_real_ledger_prevents_stale_instance_duplicate_reservation(tmp_path: Path):
    path = tmp_path / "ledger.json"
    first = ExecutionLedger(path)
    second = ExecutionLedger(path)
    first.reserve("same-id")
    try:
        second.reserve("same-id")
    except ValueError:
        pass
    else:
        raise AssertionError("stale ledger must not reserve the same REAL request_id")


def test_real_gateway_rejects_malformed_request(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    malformed = ExecutionRequest("TEST", Signal.COMPRA, float("nan"), 60, ExecutionMode.REAL, request_id="bad")
    result = gateway.execute(broker="fake", request_id="bad", request=malformed, authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_real_accepted_without_external_id_is_unknown(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", NoExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="missing-id", request=ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="missing-id"), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("missing-id") is ExecutionLedgerStatus.UNKNOWN


def test_real_authorization_rejects_non_boolean_flags():
    import pytest
    with pytest.raises(ValueError, match="booleanos"):
        RealExecutionAuthorization("auth", "audit", "fake", "adapter", 1, True)


def test_real_admission_rejects_non_boolean_prerequisite():
    import pytest
    with pytest.raises(ValueError, match="booleanos"):
        RealAdmissionBoundary().admit(
            admission_id="adm", audit_id="audit", audit_verified="yes",
            authorization_active=True, safety_ready=True,
            broker_available=True, broker_id="fake",
        )


def test_real_safety_gate_rejects_non_boolean_prerequisite():
    import pytest
    with pytest.raises(ValueError, match="booleanos"):
        RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True,
            market_healthy=True, recovery_safe=True,
            risk_approved=True, broker_available="yes",
        )


def test_real_gateway_rejects_noncanonical_request_id(tmp_path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
    )
    auth = RealExecutionAuthorization("auth", "audit", "fake", "fake-adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True,
        risk_approved=True, broker_available=True,
    )
    request = _request()
    request = type(request)(
        symbol=request.symbol, signal=request.signal, amount=request.amount,
        duration_seconds=request.duration_seconds, mode=request.mode,
        request_id=" req ",
    )
    result = gateway.execute(
        broker="fake", request_id=" req ", request=request,
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status == RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_reconciliation_never_queries_broker_for_terminal_request(tmp_path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req-terminal")
    ledger.mark_rejected("req-terminal", external_id="external-terminal")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    auth = RealExecutionAuthorization("auth", "audit", "fake", "fake-adapter", True, True)
    with pytest.raises(ValueError, match="estado incerto reconciliável"):
        gateway.reconcile_unknown(
            "req-terminal",
            broker="fake",
            authorization=auth,
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )
    assert adapter.query_calls == 0


def test_reconciliation_rejects_noncanonical_request_id_before_broker_query(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter(
        observation=ExternalOrderObservation(
            "external-2", ExternalOrderStatus.EXECUTED, "broker confirmed"
        )
    )
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("req")
    ledger.attach_external_id("req", "external-2")
    ledger.mark_unknown("req")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    with pytest.raises(ValueError, match="não canônico"):
        gateway.reconcile_unknown(
            " req ",
            broker="fake",
            authorization=_authorization(),
            reconciliation_boundary=ExternalOrderReconciliationBoundary(),
        )
    assert adapter.query_calls == 0


def test_real_admission_rejects_non_string_identifiers():
    with pytest.raises(ValueError, match="admission_id"):
        RealAdmissionBoundary().admit(
            admission_id=123, audit_id="audit", audit_verified=True,
            authorization_active=True, safety_ready=True,
            broker_available=True, broker_id="fake",
        )


def test_kill_switch_rejects_non_string_reason():
    with pytest.raises(ValueError, match="reason"):
        from core.kill_switch import KillSwitchState
        KillSwitchState(enabled=True, reason=123)
