from datetime import datetime, timezone
from pathlib import Path

from core.models import Signal
from core.kill_switch import KillSwitch
from core.p111_pre_real_audit import PreRealAuditBoundary, PreRealAuditStatus
from core.p112_real_execution_contract import RealExecutionAuthorization, RealExecutionAuthorizationBoundary
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport, RealSafetyState
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary, ReleaseAuditStatus
from core.p117_real_admission import RealAdmission, RealAdmissionBoundary, RealAdmissionStatus
from core.p118_real_monitoring import RealMonitoringBoundary, RealOutcomeStatus
from core.p119_release_closure import RealReleaseClosureBoundary, RealReleaseState
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.execution_lifecycle import ExecutionLifecycleRecord, ExecutionLifecycleState, ExecutionLifecycleStore
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus
from execution.real_reconciliation import ExternalIdentityKind, RealReconciliationEvidenceBoundary, RealReconciliationObservation


class FakeAdapter:
    adapter_id = "fake-adapter"


    def __init__(self, available=True):
        self.available = available
        self.calls = 0

    def is_available(self):
        return self.available

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "fake real execution accepted", "external-1")


class NoExternalIdAdapter:
    adapter_id = "fake-adapter"

    def is_available(self):
        return True

    def execute(self, request):
        return ExecutionResult(True, "accepted but reference missing", None)


class UnknownAdapter:
    adapter_id = "fake-adapter"

    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        raise TimeoutError("timeout after dispatch")



class FakeReconciler:
    def __init__(self, request_id: str, *, executed: bool, external_id: str | None = "external-reconciled"):
        self.request_id = request_id
        self.executed = executed
        self.external_id = external_id
        self.calls = 0
        self._boundary = RealReconciliationEvidenceBoundary._internal()

    def lookup(self, request_id: str) -> RealReconciliationObservation:
        self.calls += 1
        return self._boundary.issue(
            request_id=request_id,
            executed=self.executed,
            external_id=self.external_id if self.executed else None,
            observed_at=datetime.now(timezone.utc),
            source="fake-read-only-broker-reconciler",
            provider_capability=self._boundary.provider_capability,
            external_id_kind=ExternalIdentityKind.EXECUTION,
            provider="fake",
            account_id="demo-account",
            symbol="TEST",
            side="BUY",
            amount=10.0,
            correlation="fake-correlation",
        )


def _real_kill_switch(tmp_path: Path, ledger_path: Path | None = None) -> KillSwitch:
    return KillSwitch(
        state_path=tmp_path / "kill-switch.json",
        coordination_path=ledger_path or (tmp_path / "ledger.json"),
    )


def _reconciliation_context(request_id: str) -> dict[str, object]:
    return {
        "broker": "fake",
        "adapter_id": "fake-adapter",
        "symbol": "TEST",
        "side": "COMPRA",
        "amount": 10.0,
        "duration_seconds": 60,
        "request_id": request_id,
        "correlation": None,
    }


def _authorization():
    return RealExecutionAuthorizationBoundary._internal().issue(authorization_id="auth", audit_id="a111", broker_id="fake", adapter_id="fake-adapter", explicitly_enabled=True, real_execution_allowed=True)


def _admission(auth):
    return RealAdmissionBoundary._internal().admit(
        admission_id="adm", audit_id="a116", audit_verified=True,
        authorization_active=auth.active, safety_ready=True,
        broker_available=True, broker_id="fake",
    )


def _safety(auth):
    return RealSafetyGate._internal().evaluate(
        authorization_active=auth.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


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
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path, ledger_path=tmp_path / "real-ledger.json"))
    p119 = RealReleaseClosureBoundary._internal().close(
        release_id="release", p116_verified=p116.verified, p117_admitted=p117.admitted,
        p118_available=True, multi_broker_boundary=True,
    )
    result = gateway.execute(broker="fake", request_id="req", request=_request(), authorization=auth, admission=p117, safety=safety, release=p119)
    assert result.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1
    assert ledger.status("req") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("req") == "external-1"
    assert ExecutionLifecycleStore(tmp_path / "lifecycle.json").get("req").state is ExecutionLifecycleState.ACCEPTED
    observation = RealMonitoringBoundary().observe(observation_id="obs", request_id="req", result=result.execution)
    assert observation.status is RealOutcomeStatus.ACCEPTED
    assert p119.state is RealReleaseState.RELEASED


def test_real_authorization_is_explicit():
    try:
        RealExecutionAuthorization("a", "audit", "broker", "adapter", False, True)
    except ValueError:
        pass
    else:
        raise AssertionError("REAL must require explicit enablement")


def test_real_safety_fails_closed():
    report = RealSafetyGate._internal().evaluate(
        authorization_active=True, kill_switch_clear=False,
        market_healthy=True, recovery_safe=True, risk_approved=True, broker_available=True,
    )
    assert report.state is RealSafetyState.BLOCKED


def test_real_gateway_live_kill_switch_blocks_dispatch(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    kill_switch = _real_kill_switch(tmp_path)
    kill_switch.activate("emergência")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle, kill_switch)
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(release_id="kill-release", p116_verified=True, p117_admitted=True, p118_available=True, multi_broker_boundary=True)

    result = gateway.execute(broker="fake", request_id="kill-live", request=_request(), authorization=auth, admission=admission, safety=safety, release=release)

    assert result.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert ledger.status("kill-live") is None


def test_real_gateway_blocks_without_active_authorization(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path))
    auth = RealExecutionAuthorizationBoundary._internal().issue(authorization_id="a", audit_id="audit", broker_id="fake", adapter_id="adapter", explicitly_enabled=False, real_execution_allowed=False)
    admission = RealAdmissionBoundary._internal().admit(
        admission_id="adm", audit_id="audit", audit_verified=False,
        authorization_active=False, safety_ready=False, broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate._internal().evaluate(
        authorization_active=False, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True, broker_available=True,
    )
    release = RealReleaseClosureBoundary._internal().close(release_id="blocked-release", p116_verified=False, p117_admitted=False, p118_available=False, multi_broker_boundary=False)
    result = gateway.execute(broker="fake", request_id="blocked", request=_request(), authorization=auth, admission=admission, safety=safety, release=release)
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_unknown_is_persisted_and_retry_is_blocked(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = UnknownAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(release_id="unknown-release", p116_verified=True, p117_admitted=True, p118_available=True, multi_broker_boundary=True)
    first = gateway.execute(broker="fake", request_id="unknown-1", request=_request(), authorization=auth, admission=admission, safety=safety, release=release)
    assert first.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("unknown-1") is ExecutionLedgerStatus.UNKNOWN
    assert ExecutionLifecycleStore(tmp_path / "lifecycle.json").get("unknown-1").state is ExecutionLifecycleState.UNKNOWN
    restored = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path))
    second = restored.execute(broker="fake", request_id="unknown-1", request=_request(), authorization=auth, admission=admission, safety=safety, release=release)
    assert second.status == RealGatewayStatus.UNKNOWN


def test_real_unknown_requires_explicit_reconciliation_before_resolution(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(release_id="unknown2-release", p116_verified=True, p117_admitted=True, p118_available=True, multi_broker_boundary=True)
    result = gateway.execute(broker="fake", request_id="unknown-2", request=_request(), authorization=auth, admission=admission, safety=safety, release=release)
    assert result.status == RealGatewayStatus.UNKNOWN
    gateway.reconcile_unknown("unknown-2", reconciler=FakeReconciler("unknown-2", executed=True))
    assert ledger.status("unknown-2") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ledger.external_id("unknown-2") == "external-reconciled"
    assert ledger.status("unknown-2") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ExecutionLifecycleStore(tmp_path / "lifecycle.json").get("unknown-2").state is ExecutionLifecycleState.ACCEPTED


def test_real_reserved_after_restart_is_unknown_and_reconcilable(tmp_path: Path):
    path = tmp_path / "ledger.json"
    ExecutionLedger(path).reserve("crashed", context=_reconciliation_context("crashed"))
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(path), ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(release_id="crashed-release", p116_verified=True, p117_admitted=True, p118_available=True, multi_broker_boundary=True)
    result = gateway.execute(broker="fake", request_id="crashed", request=_request(), authorization=auth, admission=admission, safety=safety, release=release)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 0
    gateway.reconcile_unknown("crashed", reconciler=FakeReconciler("crashed", executed=False))
    assert ExecutionLedger(path).status("crashed") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED


def test_real_reservation_creates_pending_lifecycle_before_dispatch(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = UnknownAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle_path = tmp_path / "lifecycle.json"
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        ExecutionLifecycleStore(lifecycle_path),
        _real_kill_switch(tmp_path),
    )
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="pending-release",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )

    result = gateway.execute(
        broker="fake",
        request_id="pending-1",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )

    assert result.status == RealGatewayStatus.UNKNOWN
    assert adapter.calls == 1
    record = ExecutionLifecycleStore(lifecycle_path).get("pending-1")
    assert record is not None
    assert record.state is ExecutionLifecycleState.UNKNOWN


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


def test_recovery_blocks_terminal_state_without_durable_intent_context(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        '{"accepted-no-context":{"state":"ACCEPTED","external_id":"external-1"}}',
        encoding="utf-8",
    )
    lifecycle_path = tmp_path / "lifecycle.json"
    lifecycle_path.write_text(
        '[{"request_id":"accepted-no-context","state":"ACCEPTED","updated_at":"2026-09-21T00:00:00+00:00","message":"ok"}]',
        encoding="utf-8",
    )
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
        _real_kill_switch(tmp_path),
    )
    assert gateway._recovery_safe() is False


def test_recovery_blocks_durable_accepted_without_external_id(tmp_path: Path):
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text('{"accepted-no-id": "ACCEPTED"}', encoding="utf-8")
    lifecycle_path = tmp_path / "lifecycle.json"
    lifecycle_path.write_text(
        '[{"request_id":"accepted-no-id","state":"ACCEPTED","updated_at":"2026-09-21T00:00:00+00:00","message":"ok"}]',
        encoding="utf-8",
    )
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(ledger_path),
        ExecutionLifecycleStore(lifecycle_path),
        _real_kill_switch(tmp_path),
    )
    assert gateway._recovery_safe() is False


def test_real_gateway_rejects_malformed_request(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    malformed = ExecutionRequest("TEST", Signal.COMPRA, float("nan"), 60, ExecutionMode.REAL, request_id="bad")
    release = RealReleaseClosureBoundary._internal().close(release_id="bad-release", p116_verified=True, p117_admitted=True, p118_available=True, multi_broker_boundary=True)
    result = gateway.execute(broker="fake", request_id="bad", request=malformed, authorization=auth, admission=admission, safety=safety, release=release)
    assert result.status == RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_real_accepted_without_external_id_is_unknown(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", NoExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(release_id="missing-id-release", p116_verified=True, p117_admitted=True, p118_available=True, multi_broker_boundary=True)
    result = gateway.execute(broker="fake", request_id="missing-id", request=_request(), authorization=auth, admission=admission, safety=safety, release=release)
    assert result.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("missing-id") is ExecutionLedgerStatus.UNKNOWN


def test_real_release_closure_cannot_be_forged_as_released():
    from core.p119_release_closure import RealReleaseClosure, RealReleaseState

    forged = RealReleaseClosure("forged", RealReleaseState.RELEASED, "P111-P119", ())
    assert forged.released is False
    assert forged.issued_by_boundary is False


def test_real_authority_boundaries_cannot_be_constructed_externally():
    for boundary in (RealExecutionAuthorizationBoundary, RealAdmissionBoundary, RealSafetyGate, RealReleaseClosureBoundary):
        try:
            boundary()
        except ValueError:
            pass
        else:
            raise AssertionError("REAL authority boundary must require its internal issuer")


def test_real_authority_objects_cannot_be_forged_as_active():
    forged_auth = RealExecutionAuthorization("forged", "audit", "fake", "adapter", True, True)
    assert forged_auth.issued_by_boundary is False
    assert forged_auth.active is False

    from core.p117_real_admission import RealAdmission
    forged_admission = RealAdmission("adm", "audit", RealAdmissionStatus.ADMITTED, "fake", ())
    assert forged_admission.admitted is False

    from core.p114_real_safety_gate import RealSafetyReport
    forged_safety = RealSafetyReport(RealSafetyState.READY, ())
    assert forged_safety.ready is False


def test_real_gateway_rejects_duck_typed_authority_objects(tmp_path: Path):
    class Forged:
        active = True
        admitted = True
        ready = True
        released = True
        broker_id = "fake"
        adapter_id = "fake-adapter"

    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
        ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        _real_kill_switch(tmp_path),
    )
    forged = Forged()
    result = gateway.execute(
        broker="fake",
        request_id="forged-authority",
        request=_request(),
        authorization=forged,
        admission=forged,
        safety=forged,
        release=forged,
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_gateway_rejects_adapter_identity_mismatch(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path))
    auth = RealExecutionAuthorizationBoundary._internal().issue(
        authorization_id="auth-mismatch",
        audit_id="audit",
        broker_id="fake",
        adapter_id="different-adapter",
        explicitly_enabled=True,
        real_execution_allowed=True,
    )
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="mismatch-release",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )
    result = gateway.execute(
        broker="fake",
        request_id="adapter-mismatch",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )
    assert result.status is RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_real_gateway_blocks_new_dispatch_when_recovery_is_required(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    ledger.reserve("stuck")
    ledger.mark_unknown("stuck")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "stuck",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )
    lifecycle.put(
        ExecutionLifecycleRecord(
            "stuck",
            ExecutionLifecycleState.UNKNOWN,
            datetime.now(timezone.utc),
            "uncertain",
        )
    )
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle, _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="recovery-block",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )

    result = gateway.execute(
        broker="fake",
        request_id="new-request",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )

    assert result.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_gateway_rejects_request_id_mismatch(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
        ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        _real_kill_switch(tmp_path),
    )
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="request-id-mismatch",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )
    request = ExecutionRequest(
        "TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="other-id"
    )
    result = gateway.execute(
        broker="fake",
        request_id="canonical-id",
        request=request,
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )
    assert result.status is RealGatewayStatus.REJECTED
    assert adapter.calls == 0


def test_real_gateway_requires_registered_adapter_identity(tmp_path: Path):
    class UnidentifiedAdapter(FakeAdapter):
        adapter_id = None

    registry = BrokerRegistry()
    adapter = UnidentifiedAdapter()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), ExecutionLifecycleStore(tmp_path / "lifecycle.json"), _real_kill_switch(tmp_path))
    auth = RealExecutionAuthorizationBoundary._internal().issue(
        authorization_id="auth-no-id",
        audit_id="audit",
        broker_id="fake",
        adapter_id="fake-adapter",
        explicitly_enabled=True,
        real_execution_allowed=True,
    )
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="no-id-release",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )
    result = gateway.execute(
        broker="fake",
        request_id="adapter-no-id",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_recover_durable_rejection_repairs_pending_lifecycle_without_broker_query(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("durable-reject")
    ledger.mark_rejected("durable-reject")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "durable-reject",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
            "crash before lifecycle terminal write",
        )
    )
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ledger,
        lifecycle,
        _real_kill_switch(tmp_path),
    )
    gateway.recover_lifecycle_from_durable_rejection("durable-reject")
    assert ledger.status("durable-reject") is ExecutionLedgerStatus.REJECTED
    assert lifecycle.get("durable-reject").state is ExecutionLifecycleState.REJECTED


def test_reconcile_repairs_ledger_terminal_lifecycle_pending_crash_window(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("crash-accepted")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "crash-accepted",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
            "pending before crash",
        )
    )
    ledger.bind_external_id("crash-accepted", "external-reconciled")
    ledger.mark_accepted("crash-accepted")

    gateway = RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ledger,
        lifecycle,
        _real_kill_switch(tmp_path),
    )
    gateway.reconcile_unknown("crash-accepted", reconciler=FakeReconciler("crash-accepted", executed=True))

    assert ledger.status("crash-accepted") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("crash-accepted") == "external-reconciled"
    assert lifecycle.get("crash-accepted").state is ExecutionLifecycleState.ACCEPTED


def test_reconcile_repairs_ledger_rejected_lifecycle_pending_crash_window(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("crash-rejected")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "crash-rejected",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
            "pending before crash",
        )
    )
    ledger.mark_rejected("crash-rejected")

    gateway = RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ledger,
        lifecycle,
        _real_kill_switch(tmp_path),
    )
    gateway.recover_lifecycle_from_durable_rejection("crash-rejected")

    assert ledger.status("crash-rejected") is ExecutionLedgerStatus.REJECTED
    assert lifecycle.get("crash-rejected").state is ExecutionLifecycleState.REJECTED


def test_real_adapter_exception_is_unknown_not_rejected(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = UnknownAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle, _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="exception-unknown",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )

    result = gateway.execute(
        broker="fake",
        request_id="adapter-timeout",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )

    assert result.status is RealGatewayStatus.UNKNOWN
    assert ledger.status("adapter-timeout") is ExecutionLedgerStatus.UNKNOWN
    assert lifecycle.get("adapter-timeout").state is ExecutionLifecycleState.UNKNOWN
    assert adapter.calls == 1


def test_real_accept_persist_crash_keeps_request_uncertain_until_reconciliation(tmp_path: Path):
    class FailOnTerminalLifecycleStore(ExecutionLifecycleStore):
        def __init__(self, path):
            super().__init__(path)
            self.calls = 0

        def put(self, record):
            self.calls += 1
            if self.calls == 2:
                raise OSError("simulated lifecycle persistence crash")
            return super().put(record)

    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = FailOnTerminalLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle, _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="persist-crash-accepted",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )

    result = gateway.execute(
        broker="fake",
        request_id="persist-crash-accepted",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )

    assert result.status is RealGatewayStatus.UNKNOWN
    assert ledger.status("persist-crash-accepted") is ExecutionLedgerStatus.ACCEPTED
    assert lifecycle.get("persist-crash-accepted").state is ExecutionLifecycleState.PENDING
    assert adapter.calls == 1

    blocked = gateway.execute(
        broker="fake",
        request_id="new-after-crash",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )
    assert blocked.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 1

    gateway.reconcile_unknown("persist-crash-accepted", reconciler=FakeReconciler("persist-crash-accepted", executed=True, external_id="external-1"))
    assert ledger.status("persist-crash-accepted") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.external_id("persist-crash-accepted") == "external-1"
    assert lifecycle.get("persist-crash-accepted").state is ExecutionLifecycleState.ACCEPTED


def test_real_reject_persist_crash_keeps_request_uncertain_until_reconciliation(tmp_path: Path):
    class RejectingAdapter(FakeAdapter):
        def execute(self, request):
            self.calls += 1
            return ExecutionResult(False, "broker rejeitou", None)

    class FailOnTerminalLifecycleStore(ExecutionLifecycleStore):
        def __init__(self, path):
            super().__init__(path)
            self.calls = 0

        def put(self, record):
            self.calls += 1
            if self.calls == 2:
                raise OSError("simulated lifecycle persistence crash")
            return super().put(record)

    registry = BrokerRegistry()
    adapter = RejectingAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = FailOnTerminalLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle, _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="persist-crash-rejected",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )

    result = gateway.execute(
        broker="fake",
        request_id="persist-crash-rejected",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )

    assert result.status is RealGatewayStatus.UNKNOWN
    assert ledger.status("persist-crash-rejected") is ExecutionLedgerStatus.REJECTED
    assert lifecycle.get("persist-crash-rejected").state is ExecutionLifecycleState.PENDING
    assert adapter.calls == 1

    blocked = gateway.execute(
        broker="fake",
        request_id="new-after-reject-crash",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )
    assert blocked.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 1

    # Durable local rejection is conclusive; recovery must repair only Lifecycle.
    gateway.recover_lifecycle_from_durable_rejection("persist-crash-rejected")
    assert ledger.status("persist-crash-rejected") is ExecutionLedgerStatus.REJECTED
    assert lifecycle.get("persist-crash-rejected").state is ExecutionLifecycleState.REJECTED


def test_reconcile_ledger_only_unknown_reconstructs_terminal_lifecycle_without_dispatch(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("ledger-only", context=_reconciliation_context("ledger-only"))
    ledger.mark_unknown("ledger-only")

    gateway = RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ledger,
        lifecycle,
        _real_kill_switch(tmp_path),
    )
    gateway.reconcile_unknown("ledger-only", reconciler=FakeReconciler("ledger-only", executed=True))
    assert ledger.status("ledger-only") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ledger.external_id("ledger-only") == "external-reconciled"
    assert lifecycle.get("ledger-only").state is ExecutionLifecycleState.ACCEPTED


def test_real_reconciliation_rejects_naked_boolean(tmp_path: Path):
    registry = BrokerRegistry()
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
        ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
        _real_kill_switch(tmp_path),
    )
    ExecutionLedger(tmp_path / "ledger.json").reserve("bool-evidence")
    try:
        gateway.reconcile_unknown("bool-evidence", executed=True)
    except TypeError:
        pass
    else:
        raise AssertionError("reconciliação REAL não deve aceitar booleano como evidência")


def test_real_reconciliation_rejects_mismatched_external_observation(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("observed-request", context=_reconciliation_context("observed-request"))
    ledger.mark_unknown("observed-request")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ledger,
        lifecycle,
        _real_kill_switch(tmp_path),
    )

    class WrongRequestReconciler:
        def lookup(self, request_id: str) -> RealReconciliationObservation:
            return RealReconciliationObservation(
                request_id="different-request",
                executed=True,
                external_id="external-1",
                observed_at=datetime.now(timezone.utc),
                source="fake-read-only-broker-reconciler",
            )

    try:
        gateway.reconcile_unknown("observed-request", reconciler=WrongRequestReconciler())
    except ValueError as exc:
        assert "evidência externa" in str(exc)
    else:
        raise AssertionError("evidência de outro request_id não pode reconciliar esta execução")
    assert ledger.status("observed-request") is ExecutionLedgerStatus.UNKNOWN
    assert lifecycle.get("observed-request") is None

def test_durable_rejection_recovery_does_not_query_broker(tmp_path: Path):
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("local-reject")
    ledger.mark_rejected("local-reject")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "local-reject",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
            "crash before lifecycle terminal write",
        )
    )

    class ExplodingReconciler:
        def lookup(self, request_id: str):
            raise AssertionError("rejeição durável não deve consultar o broker")

    gateway = RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ledger,
        lifecycle,
        _real_kill_switch(tmp_path),
    )
    gateway.reconcile_unknown("local-reject", reconciler=ExplodingReconciler())

    assert lifecycle.get("local-reject").state is ExecutionLifecycleState.REJECTED
    assert ledger.status("local-reject") is ExecutionLedgerStatus.REJECTED


def test_reconciliation_evidence_capability_is_instance_bound():
    first = RealReconciliationEvidenceBoundary._internal()
    second = RealReconciliationEvidenceBoundary._internal()
    try:
        second.issue(
            request_id="cross-boundary",
            executed=False,
            external_id=None,
            observed_at=datetime.now(timezone.utc),
            source="fake",
            provider_capability=first.provider_capability,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("provider capability must not cross evidence-boundary instances")


def test_reconciliation_observation_constructor_cannot_mark_itself_issued():
    observation = RealReconciliationObservation(
        request_id="forged",
        executed=False,
        external_id=None,
        observed_at=datetime.now(timezone.utc),
        source="forged",
    )
    assert observation.issued_by_boundary is False


def test_reconciliation_evidence_boundary_rejects_forged_provider_capability():
    boundary = RealReconciliationEvidenceBoundary._internal()
    try:
        boundary.issue(
            request_id="forged",
            executed=False,
            external_id=None,
            observed_at=datetime.now(timezone.utc),
            source="fake",
            provider_capability=object(),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("evidence issuance must reject a forged provider capability")


def test_recovery_can_persist_external_identity_discovered_after_bind_crash(tmp_path: Path):
    class BindCrashLedger(ExecutionLedger):
        def __init__(self, path):
            self.bind_attempts = 0
            super().__init__(path)

        def bind_external_id(self, request_id: str, external_id: str) -> None:
            self.bind_attempts += 1
            if self.bind_attempts == 1:
                raise OSError("simulated crash during external-id persistence")
            return super().bind_external_id(request_id, external_id)

    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = BindCrashLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ledger, lifecycle, _real_kill_switch(tmp_path))
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="bind-crash-recovery",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )

    result = gateway.execute(
        broker="fake",
        request_id="bind-crash",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )

    assert result.status is RealGatewayStatus.UNKNOWN
    assert ledger.status("bind-crash") is ExecutionLedgerStatus.RESERVED
    assert lifecycle.get("bind-crash").state is ExecutionLifecycleState.PENDING
    assert ledger.external_id("bind-crash") is None
    assert adapter.calls == 1

    boundary = RealReconciliationEvidenceBoundary._internal()
    observation = boundary.issue(
        request_id="bind-crash",
        executed=True,
        external_id="external-1",
        observed_at=datetime.now(timezone.utc),
        source="read-only-broker-reconciler",
        provider_capability=boundary.provider_capability,
        external_id_kind=ExternalIdentityKind.EXECUTION,
        provider="fake",
        account_id="demo-account",
        symbol="TEST",
        side="BUY",
        amount=10.0,
        correlation="fake-correlation",
    )

    class ReadOnlyReconciler:
        def lookup(self, request_id: str):
            return observation

    gateway.reconcile_unknown("bind-crash", reconciler=ReadOnlyReconciler())

    assert ledger.status("bind-crash") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ledger.external_id("bind-crash") == "external-1"
    assert lifecycle.get("bind-crash").state is ExecutionLifecycleState.ACCEPTED
    assert adapter.calls == 1


def test_real_authorization_boundary_cannot_be_constructed_externally():
    try:
        RealExecutionAuthorizationBoundary()
    except ValueError as exc:
        assert "emissor REAL interno" in str(exc)
    else:
        raise AssertionError("emissor REAL não pode ser instanciado externamente")


def test_real_authority_boundaries_cannot_be_constructed_externally():
    for boundary, marker in (
        (RealAdmissionBoundary, "admissão REAL"),
        (RealSafetyGate, "segurança REAL"),
        (RealReleaseClosureBoundary, "release REAL"),
    ):
        try:
            boundary()
        except ValueError as exc:
            assert marker in str(exc)
        else:
            raise AssertionError("boundary REAL não pode ser instanciada externamente")


def test_real_gateway_blocks_same_thread_adapter_reentry_without_second_dispatch(tmp_path: Path):
    class ReentrantAdapter:
        adapter_id = "fake-adapter"

        def __init__(self):
            self.calls = 0
            self.gateway = None
            self.nested_kwargs = None
            self.nested_result = None

        def is_available(self):
            return True

        def execute(self, request):
            self.calls += 1
            self.nested_result = self.gateway.execute(**self.nested_kwargs)
            return ExecutionResult(True, "outer execution accepted", "external-outer")

    registry = BrokerRegistry()
    adapter = ReentrantAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger, lifecycle, _real_kill_switch(tmp_path)
    )
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="reentry-release",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )
    adapter.gateway = gateway
    adapter.nested_kwargs = dict(
        broker="fake",
        request_id="nested-request",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )

    result = gateway.execute(
        broker="fake",
        request_id="outer-request",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )

    assert result.status is RealGatewayStatus.ADMITTED
    assert adapter.calls == 1
    assert adapter.nested_result is not None
    assert adapter.nested_result.status is RealGatewayStatus.BLOCKED
    assert ledger.status("outer-request") is ExecutionLedgerStatus.ACCEPTED
    assert ledger.status("nested-request") is None


def test_real_reconciliation_reentry_is_rejected_without_state_mutation(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger, lifecycle, _real_kill_switch(tmp_path)
    )
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="reconcile-reentry-release",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )
    result = gateway.execute(
        broker="fake",
        request_id="reconcile-reentry",
        request=_request(),
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )
    assert result.status is RealGatewayStatus.UNKNOWN

    class ReentrantReconciler:
        def lookup(self, request_id: str):
            gateway.reconcile_unknown(request_id, reconciler=self)
            raise AssertionError("lookup should not continue after reentry rejection")

    try:
        gateway.reconcile_unknown(
            "reconcile-reentry", reconciler=ReentrantReconciler()
        )
    except RuntimeError as exc:
        assert "reentrada proibida" in str(exc)
    else:
        raise AssertionError("reconciliation reentry must be rejected")

    assert ledger.status("reconcile-reentry") is ExecutionLedgerStatus.UNKNOWN
    assert lifecycle.get("reconcile-reentry").state is ExecutionLifecycleState.UNKNOWN


def test_real_gateway_canonicalizes_request_id_before_broker_dispatch(tmp_path: Path):
    registry = BrokerRegistry()
    adapter = FakeAdapter()
    registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger, lifecycle, _real_kill_switch(tmp_path)
    )
    auth = _authorization()
    admission = _admission(auth)
    safety = _safety(auth)
    release = RealReleaseClosureBoundary._internal().close(
        release_id="canonical-id-release",
        p116_verified=True,
        p117_admitted=True,
        p118_available=True,
        multi_broker_boundary=True,
    )
    request = ExecutionRequest(
        "TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id="  broker-id  "
    )

    result = gateway.execute(
        broker="fake",
        request_id="  broker-id  ",
        request=request,
        authorization=auth,
        admission=admission,
        safety=safety,
        release=release,
    )

    assert result.status is RealGatewayStatus.ADMITTED
    assert ledger.records() == ("broker-id",)
    assert ledger.external_id("broker-id") == "external-1"
    assert ledger.status("  broker-id  ") is ExecutionLedgerStatus.ACCEPTED


def test_real_gateway_rejects_ephemeral_kill_switch_at_composition(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")

    try:
        RealExecutionGateway(
            BrokerAdapterGateway(registry),
            ledger,
            lifecycle,
            KillSwitch(),
        )
    except ValueError as exc:
        assert "durável" in str(exc)
    else:
        raise AssertionError("REAL must reject an ephemeral kill switch")


def test_real_gateway_rejects_kill_switch_with_different_coordination_identity(tmp_path: Path):
    registry = BrokerRegistry()
    registry.register("fake", FakeAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    mismatched = KillSwitch(
        state_path=tmp_path / "kill-switch.json",
        coordination_path=tmp_path / "different-coordination.json",
    )

    try:
        RealExecutionGateway(
            BrokerAdapterGateway(registry),
            ledger,
            lifecycle,
            mismatched,
        )
    except ValueError as exc:
        assert "coordenação do Ledger" in str(exc)
    else:
        raise AssertionError("REAL must share the Ledger coordination identity")


def test_reconciliation_non_terminal_outcomes_do_not_close_unknown(tmp_path: Path):
    """A broker query that is inconclusive must leave REAL execution UNKNOWN."""
    from execution.real_reconciliation import ReconciliationOutcome

    ledger = ExecutionLedger(tmp_path / "ledger.json")
    lifecycle = ExecutionLifecycleStore(tmp_path / "lifecycle.json")
    ledger.reserve("nonterminal", context=_reconciliation_context("nonterminal"))
    ledger.mark_unknown("nonterminal")
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(BrokerRegistry()),
        ledger,
        lifecycle,
        _real_kill_switch(tmp_path),
    )
    boundary = RealReconciliationEvidenceBoundary._internal()

    class Reconciler:
        def __init__(self, outcome):
            self.outcome = outcome

        def lookup(self, request_id):
            return boundary.issue(
                request_id=request_id,
                executed=False,
                external_id=None,
                outcome=self.outcome,
                observed_at=datetime.now(timezone.utc),
                source="read-only-broker-reconciler",
                provider_capability=boundary.provider_capability,
            )

    for outcome in (
        ReconciliationOutcome.NOT_FOUND,
        ReconciliationOutcome.NOT_VISIBLE_YET,
        ReconciliationOutcome.QUERY_FAILED,
        ReconciliationOutcome.AMBIGUOUS,
    ):
        gateway.reconcile_unknown("nonterminal", reconciler=Reconciler(outcome))
        assert ledger.status("nonterminal") is ExecutionLedgerStatus.UNKNOWN
        assert lifecycle.get("nonterminal") is None


def test_reconciliation_requires_explicit_external_identity_kind_for_execution(tmp_path: Path):
    from execution.real_reconciliation import validate_observation

    boundary = RealReconciliationEvidenceBoundary._internal()
    observation = boundary.issue(
        request_id="identity-kind",
        executed=True,
        external_id="123",
        observed_at=datetime.now(timezone.utc),
        source="read-only-broker-reconciler",
        provider_capability=boundary.provider_capability,
    )
    assert not validate_observation("identity-kind", observation)
