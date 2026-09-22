from pathlib import Path
from datetime import datetime, timezone

from core.models import Signal
from core.operation_memory import OperationMemory
from core.recovery_coordinator import RecoveryCoordinator
from core.runtime_checkpoint import RuntimeCheckpointStore
from core.kill_switch import KillSwitch
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
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus, ExternalOrderQueryPort


class FakeAdapter:
    adapter_id = "fake-adapter"

    def __init__(self, available=True):
        self.available = available
        self.supports_real_execution = True
        self.calls = 0

    def is_available(self):
        return self.available

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "fake real execution accepted", "external-1")


class NoExternalIdAdapter:
    adapter_id = "fake-adapter"
    supports_real_execution = True

    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(True, "accepted but reference missing", None)


class RejectedWithExternalIdAdapter:
    adapter_id = "fake-adapter"
    supports_real_execution = True

    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(False, "adapter reported rejection after broker response", "external-rejected-1")


class UnknownAdapter:
    adapter_id = "fake-adapter"
    supports_real_execution = True

    def is_available(self):
        return True

    def execute(self, request):
        raise TimeoutError("timeout after dispatch")


def _authorization():
    return RealExecutionAuthorization("auth", "a111", "fake", "fake-adapter", True, True)


def _admission(auth):
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="a116", audit_verified=True,
        authorization_active=auth.active, safety_ready=True,
        broker_available=True, broker_id="fake",
    )


def _safety(auth):
    return RealSafetyGate().evaluate(
        authorization_active=auth.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )


def _request(request_id="req"):
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id)


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
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "real-ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    result = gateway.execute(broker="fake", request_id="req", request=_request("req"), authorization=auth, admission=p117, safety=safety)
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
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), kill_switch=KillSwitch())
    auth = RealExecutionAuthorization("a", "audit", "fake", "adapter", False, False)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=False,
        authorization_active=False, safety_ready=False, broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=False, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True, broker_available=True,
    )
    result = gateway.execute(broker="fake", request_id="blocked", request=_request("blocked"), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_gateway_rejects_adapter_identity_mismatch(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), kill_switch=KillSwitch())
    auth = RealExecutionAuthorization("auth", "a111", "fake", "wrong-adapter", True, True)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="a116", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )
    result = gateway.execute(
        broker="fake", request_id="adapter-mismatch", request=_request("adapter-mismatch"),
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status is RealGatewayStatus.UNKNOWN
    assert adapter.calls == 0
    assert ExecutionLedger(tmp_path / "ledger.json").status("adapter-mismatch") is ExecutionLedgerStatus.UNKNOWN


def test_real_gateway_rejects_admission_broker_mismatch(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), kill_switch=KillSwitch())
    auth = _authorization()
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="a111", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="other-broker",
    )
    safety = _safety(auth)
    result = gateway.execute(
        broker="fake", request_id="admission-broker-mismatch", request=_request("admission-broker-mismatch"),
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status is RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_real_gateway_blocks_admission_audit_mismatch(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), kill_switch=KillSwitch())
    auth = _authorization()
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="different-audit", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
    )
    safety = _safety(auth)
    result = gateway.execute(
        broker="fake", request_id="admission-audit-mismatch", request=_request("admission-audit-mismatch"),
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_gateway_does_not_reserve_when_lifecycle_exists_without_ledger(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "real-ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "real-lifecycle.json")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "lifecycle-only",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
        )
    )
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle=lifecycle,
        kill_switch=KillSwitch(),
    )
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(
        broker="fake",
        request_id="lifecycle-only",
        request=_request("lifecycle-only"),
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert result.status is RealGatewayStatus.UNKNOWN
    assert adapter.calls == 0
    assert ledger.status("lifecycle-only") is None


def test_real_rejected_with_external_id_becomes_unknown(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", RejectedWithExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)

    result = gateway.execute(
        broker="fake", request_id="ambiguous-reject", request=_request("ambiguous-reject"),
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status is RealGatewayStatus.UNKNOWN
    assert ledger.status("ambiguous-reject") is ExecutionLedgerStatus.UNKNOWN
    assert ledger.external_id("ambiguous-reject") == "external-rejected-1"


def test_real_unknown_is_persisted_and_retry_is_blocked(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = UnknownAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    first = gateway.execute(broker="fake", request_id="unknown-1", request=_request("unknown-1"), authorization=auth, admission=admission, safety=safety)
    assert first.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("unknown-1") is ExecutionLedgerStatus.UNKNOWN
    restored = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), kill_switch=KillSwitch())
    second = restored.execute(broker="fake", request_id="unknown-1", request=_request("unknown-1"), authorization=auth, admission=admission, safety=safety)
    assert second.status == RealGatewayStatus.UNKNOWN


def test_real_unknown_requires_explicit_reconciliation_before_resolution(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="unknown-2", request=_request("unknown-2"), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    ledger.attach_external_id("unknown-2", "external-recovered-2")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    lifecycle.put(ExecutionLifecycleRecord("unknown-2", ExecutionLifecycleState.UNKNOWN, datetime.now(timezone.utc)))
    class Query(ExternalOrderQueryPort):
        def query_order(self, external_id):
            return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, "reconciled", "fake")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle=lifecycle, kill_switch=KillSwitch())
    gateway.reconcile_unknown("unknown-2", query_port=Query())
    assert ledger.status("unknown-2") is ExecutionLedgerStatus.RECONCILED_EXECUTED


def test_real_reserved_after_restart_is_unknown_and_reconcilable(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ExecutionLedger(path).reserve("crashed")
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(path)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="crashed", request=_request("crashed"), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 0
    ledger.attach_external_id("crashed", "external-recovered-crashed")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    lifecycle.put(ExecutionLifecycleRecord("crashed", ExecutionLifecycleState.UNKNOWN, datetime.now(timezone.utc)))
    class Query(ExternalOrderQueryPort):
        def query_order(self, external_id):
            return ExternalOrderObservation(external_id, ExternalOrderStatus.NOT_EXECUTED, "not executed", "fake")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger, lifecycle=lifecycle, kill_switch=KillSwitch()
    )
    try:
        gateway.reconcile_unknown("crashed", query_port=Query())
    except ValueError as exc:
        assert "Ledger UNKNOWN" in str(exc)
    else:
        raise AssertionError("RESERVED não pode ser reconciliado enquanto pode representar dispatch em andamento")
    ledger.mark_unknown("crashed")
    gateway.reconcile_unknown("crashed", query_port=Query())
    assert ExecutionLedger(path).status("crashed") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED
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


def test_real_gateway_rejects_aguardar_before_adapter(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(
        broker="fake", request_id="aguardar", request=ExecutionRequest("TEST", Signal.AGUARDAR, 10.0, 60, ExecutionMode.REAL, "aguardar"),
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status is RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_real_gateway_requires_matching_request_identity(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(
        broker="fake", request_id="gateway-id",
        request=ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, "different-id"),
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status is RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_real_gateway_rejects_malformed_request(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    malformed = ExecutionRequest("TEST", Signal.COMPRA, float("nan"), 60, ExecutionMode.REAL)
    result = gateway.execute(broker="fake", request_id="bad", request=malformed, authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_real_accepted_without_external_id_is_unknown(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", NoExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="missing-id", request=_request("missing-id"), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("missing-id") is ExecutionLedgerStatus.UNKNOWN


def test_explicit_reconciliation_projects_lifecycle(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle,
        KillSwitch(),
    )
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)

    result = gateway.execute(
        broker="fake",
        request_id="unknown-lifecycle",
        request=_request("unknown-lifecycle"),
        authorization=auth,
        admission=admission,
        safety=safety,
    )
    assert result.status == RealGatewayStatus.UNKNOWN
    ledger.attach_external_id("unknown-lifecycle", "external-recovered-lifecycle")
    class Query(ExternalOrderQueryPort):
        def query_order(self, external_id):
            return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, "reconciled", "fake")
    gateway.reconcile_unknown("unknown-lifecycle", query_port=Query())
    assert lifecycle.get("unknown-lifecycle").state.name == "ACCEPTED"


def test_real_terminal_ledger_survives_lifecycle_projection_failure(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle=lifecycle, kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)

    original = gateway._mark_lifecycle
    def fail_once(request_id, state, message):
        raise OSError("simulated lifecycle crash")
    gateway._mark_lifecycle = fail_once

    result = gateway.execute(
        broker="fake", request_id="projection-crash",
        request=_request("projection-crash"),
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status is RealGatewayStatus.UNKNOWN
    assert ledger.status("projection-crash") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("projection-crash") is not None

    gateway._mark_lifecycle = original
    coordinator = RecoveryCoordinator(
        checkpoint_store=RuntimeCheckpointStore(tmp_path / "checkpoint.json"),
        lifecycle_store=lifecycle,
        execution_ledger=ledger,
        memory=OperationMemory(),
    )
    coordinator.repair_terminal_lifecycle_projection("projection-crash")
    assert lifecycle.get("projection-crash").state.name == "ACCEPTED"


def test_real_reconciliation_without_external_reference_stays_uncertain(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle=lifecycle, kill_switch=KillSwitch())
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="no-proof", request=_request("no-proof"), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    class Query(ExternalOrderQueryPort):
        def query_order(self, external_id):
            raise AssertionError("query must not run without durable external_id")
    try:
        gateway.reconcile_unknown("no-proof", query_port=Query())
    except ValueError as exc:
        assert "external_id" in str(exc)
    else:
        raise AssertionError("REAL não pode ser fechado como executado sem referência externa durável")
    assert ledger.status("no-proof") is ExecutionLedgerStatus.UNKNOWN
def test_real_monitoring_does_not_promote_accepted_without_external_id():
    observation = RealMonitoringBoundary().observe(
        observation_id="obs-missing-proof",
        request_id="req-missing-proof",
        result=ExecutionResult(True, "accepted but no reference", None),
    )
    assert observation.status is RealOutcomeStatus.UNKNOWN
    assert observation.external_id is None
    assert observation.observed_at.tzinfo is not None
    assert observation.source == "real_execution_gateway"


def test_real_monitoring_requires_provenance_fields():
    try:
        from datetime import datetime
        from core.p118_real_monitoring import RealExecutionObservation
        RealExecutionObservation(
            "obs", "req", RealOutcomeStatus.ACCEPTED, "external-1", "ok",
            datetime.now(), "real_execution_gateway",
        )
    except ValueError as exc:
        assert "timezone" in str(exc)
    else:
        raise AssertionError("observação sem timezone não pode ser evidência válida")


def test_real_monitoring_rejects_cross_broker_observation(tmp_path: Path):
    from core.p121_external_order_reconciliation import (
        ExternalOrderObservation,
        ExternalOrderQueryPort,
        ExternalOrderReconciliationBoundary,
        ExternalOrderStatus,
    )

    class Query(ExternalOrderQueryPort):
        def query_order(self, external_id):
            return ExternalOrderObservation(external_id, ExternalOrderStatus.EXECUTED, "ok", "broker-b")

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("cross-broker", broker_id="broker-a")
    ledger.attach_external_id("cross-broker", "ext-1")
    ledger.mark_unknown("cross-broker")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "cross-broker", ExecutionLifecycleState.UNKNOWN, datetime.now(timezone.utc)
        )
    )

    try:
        ExternalOrderReconciliationBoundary().reconcile_request(
            request_id="cross-broker",
            ledger=ledger,
            lifecycle=lifecycle,
            query_port=Query(),
        )
    except ValueError as exc:
        assert "broker" in str(exc)
    else:
        raise AssertionError("reconciliação não pode aceitar evidência de outro broker")
