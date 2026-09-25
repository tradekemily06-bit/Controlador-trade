from pathlib import Path

from core.models import Signal
from core.p111_pre_real_audit import PreRealAuditBoundary, PreRealAuditStatus
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyState
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary, ReleaseAuditStatus
from core.p117_real_admission import RealAdmissionBoundary, RealAdmissionStatus
from core.p118_real_monitoring import RealMonitoringBoundary, RealOutcomeStatus
from core.p119_release_closure import RealReleaseClosureBoundary, RealReleaseState
from core.p121_external_order_reconciliation import ExternalOrderObservation, ExternalOrderStatus
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus
from security.production_operation_gate import ProductionOperationGate
from storage.production_boundary import ProductionStoragePolicy


class FakeAdapter:
    def __init__(self, available=True):
        self.available = available
        self.calls = 0

    def is_available(self):
        return self.available

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "fake real execution accepted", "external-1")


class NoExternalIdAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(True, "accepted but reference missing", None)


class UnknownAdapter:
    def is_available(self):
        return True

    def execute(self, request):
        raise TimeoutError("timeout after dispatch")


class TrustedOrderQuery:
    def __init__(self, observation):
        self.observation = observation

    def query_order(self, external_id, *, broker_id, account_id):
        assert external_id == self.observation.external_id
        assert broker_id == self.observation.broker_id
        assert account_id == self.observation.account_id
        return self.observation


def _gateway(registry, ledger, external_order_query=None):
    production_gate = ProductionOperationGate(
        ProductionStoragePolicy(required=True, provider_configured=True, tenant_scoped=True, durable=True)
    )
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        external_order_query=external_order_query,
        production_gate=production_gate,
    )


def _authorization():
    return RealExecutionAuthorization("auth", "a111", "fake", "fake-adapter", True, True, "user-a", "tenant-a", "account-a")


def _admission(auth):
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="a116", audit_verified=True,
        authorization_active=auth.active, safety_ready=True,
        broker_available=True, broker_id="fake", subject_id=auth.subject_id,
        tenant_id=auth.tenant_id, account_id=auth.account_id,
    )


def _safety(auth):
    return RealSafetyGate().evaluate(
        authorization_active=auth.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, account_id="account-a")


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
    gateway = _gateway(registry, ledger)
    result = gateway.execute(broker="fake", request_id="req", request=_request(), authorization=auth, admission=p117, safety=safety)
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
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"))
    auth = RealExecutionAuthorization("a", "audit", "fake", "adapter", False, False)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=False,
        authorization_active=False, safety_ready=False, broker_available=True, broker_id="fake",
        subject_id="user-a", tenant_id="tenant-a", account_id="account-a",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=False, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True, broker_available=True,
    )
    result = gateway.execute(broker="fake", request_id="blocked", request=_request(), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_unknown_is_persisted_and_retry_is_blocked(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = UnknownAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    first = gateway.execute(broker="fake", request_id="unknown-1", request=_request(), authorization=auth, admission=admission, safety=safety)
    assert first.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("unknown-1") is ExecutionLedgerStatus.UNKNOWN
    restored = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"))
    second = restored.execute(broker="fake", request_id="unknown-1", request=_request(), authorization=auth, admission=admission, safety=safety)
    assert second.status == RealGatewayStatus.UNKNOWN


def test_real_unknown_requires_explicit_reconciliation_before_resolution(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="unknown-2", request=_request(), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    try:
        gateway.reconcile_unknown("unknown-2", executed=True, evidence_id="broker-event-unknown-2", evidence_source="fake-broker")
    except RuntimeError:
        pass
    else:
        raise AssertionError("manual REAL reconciliation must be blocked")
    assert ledger.status("unknown-2") is ExecutionLedgerStatus.UNKNOWN


def test_real_reserved_after_restart_is_unknown_and_reconcilable(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ExecutionLedger(path).reserve("crashed")
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = _gateway(registry, ExecutionLedger(path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="crashed", request=_request(), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 0
    try:
        gateway.reconcile_unknown("crashed", executed=False, evidence_id="broker-event-crashed", evidence_source="fake-broker")
    except RuntimeError:
        pass
    else:
        raise AssertionError("manual REAL reconciliation must be blocked")
    assert ExecutionLedger(path).status("crashed") is ExecutionLedgerStatus.RESERVED


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
    malformed = ExecutionRequest("TEST", Signal.COMPRA, float("nan"), 60, ExecutionMode.REAL, account_id="account-a")
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
    result = gateway.execute(broker="fake", request_id="missing-id", request=_request(), authorization=auth, admission=admission, safety=safety)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("missing-id") is ExecutionLedgerStatus.UNKNOWN


def test_external_observation_resolves_unknown_by_persisted_external_identity(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve_real("req-ext", broker_id="fake", symbol="EURUSD", account_id="account-a")
    ledger.mark_unknown("req-ext")
    ledger.bind_external_id("req-ext", external_id="ext-42")
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    observation = ExternalOrderObservation("ext-42", ExternalOrderStatus.EXECUTED, "broker confirms execution", "fake", "account-a")
    gateway = _gateway(registry, ledger, external_order_query=TrustedOrderQuery(observation))
    result = gateway.reconcile_external_observation(
        "req-ext",
        observation,
        evidence_id="obs-ext-42",
        evidence_source="fake-broker-query",
    )
    assert result.reconciled is True
    assert ledger.status("req-ext") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ledger.reconciliation_evidence("req-ext") == {
        "evidence_id": "obs-ext-42",
        "evidence_source": "fake-broker-query",
    }


def test_external_observation_cannot_reconcile_unknown_without_matching_external_identity(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve_real("req-ext", broker_id="fake", symbol="EURUSD")
    ledger.mark_unknown("req-ext")
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    observation = ExternalOrderObservation("ext-other", ExternalOrderStatus.EXECUTED, "different broker order")
    try:
        gateway.reconcile_external_observation(
            "req-ext",
            observation,
            evidence_id="obs-other",
            evidence_source="fake-broker-query",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("external observation without a linked external_id must not mutate the ledger")
    assert ledger.status("req-ext") is ExecutionLedgerStatus.UNKNOWN


def test_real_unknown_persistence_failure_leaves_reserved_replay_block(tmp_path: Path, monkeypatch):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger)
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)

    def fail_mark_unknown(_request_id):
        raise OSError("falha de persistência simulada")

    monkeypatch.setattr(ledger, "mark_unknown", fail_mark_unknown)
    result = gateway.execute(
        broker="fake",
        request_id="persist-fail",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("persist-fail") is ExecutionLedgerStatus.RESERVED


def test_real_gateway_blocks_mismatched_identity_scope(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"))
    auth = _authorization()
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="a116", audit_verified=True,
        authorization_active=True, safety_ready=True,
        broker_available=True, broker_id="fake",
        subject_id="other-user", tenant_id=auth.tenant_id, account_id=auth.account_id,
    )
    safety = _safety(auth)
    result = gateway.execute(
        broker="fake", request_id="scope-mismatch", request=_request(),
        authorization=auth, admission=admission, safety=safety,
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
