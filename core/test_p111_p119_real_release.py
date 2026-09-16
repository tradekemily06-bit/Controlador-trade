from pathlib import Path

from core.decision_snapshot import DecisionSnapshot
from core.models import Signal
from core.operational_state import OperationalState
from core.risk_state_fingerprint import risk_state_identity
from core.p111_pre_real_audit import PreRealAuditBoundary, PreRealAuditStatus
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport, RealSafetyState
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary, ReleaseAuditStatus
from core.p117_real_admission import RealAdmissionBoundary, RealAdmissionStatus
from core.p118_real_monitoring import RealMonitoringBoundary, RealOutcomeStatus
from core.p119_release_closure import RealReleaseClosureBoundary, RealReleaseState
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
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


class FakeRiskStateProvider:
    def __init__(self, state: OperationalState):
        self.state = state

    def current_risk_state(self) -> OperationalState:
        return self.state


class FakeRealSafetyProvider:
    def __init__(self, report: RealSafetyReport):
        self.report = report

    def current_real_safety(self) -> RealSafetyReport:
        return self.report


def _risk_state():
    return OperationalState(
        balance=1000.0,
        equity=1000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        trades_today=0,
        consecutive_losses=0,
        open_positions=0,
        net_position=0.0,
        exposure=0.0,
        market_open=True,
    )


def _snapshot():
    state = _risk_state()
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None, operational_state_available=True,
        trades_today=state.trades_today, consecutive_losses=state.consecutive_losses,
        symbol="TEST", timeframe="5m", risk_state_identity=risk_state_identity(state),
    )


def _gateway(registry, ledger):
    auth = _authorization()
    return RealExecutionGateway(
        BrokerAdapterGateway(registry), ledger,
        FakeRiskStateProvider(_risk_state()), FakeRealSafetyProvider(_safety(auth)),
    )


def _authorization():
    return RealExecutionAuthorization("auth", "a116", "fake", "fake-adapter", True, True)


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


def _request():
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL)


def test_p111_p116_p117_p119_positive_flow(tmp_path: Path):
    p111 = PreRealAuditBoundary().audit(
        audit_id="a111", p110_decision="VALIDATED", safety_verified=True,
        risk_verified=True, gateway_present=True, broker_boundary_present=True,
    )
    assert p111.status is PreRealAuditStatus.VERIFIED
    auth = _authorization(); safety = _safety(auth)
    assert safety.state is RealSafetyState.READY
    shadow = ShadowValidationBoundary().validate(
        validation_id="shadow", adapter_available=True, real_safety_ready=True,
        duplicate_blocked=True, kill_switch_blocked=True, real_mode_rejected_by_shadow=True,
    )
    assert shadow.passed
    p116 = RealReleaseAuditBoundary().audit(
        audit_id="a116", pre_real_verified=p111.verified,
        shadow_passed=shadow.passed, safety_ready=safety.ready,
        broker_boundary_ready=True, explicit_real_contract=True,
    )
    assert p116.status is ReleaseAuditStatus.VERIFIED
    p117 = _admission(auth); assert p117.status is RealAdmissionStatus.ADMITTED
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "real-ledger.json"); gateway = _gateway(registry, ledger)
    request = _request()
    request = type(request)(request.symbol, request.signal, request.amount, request.duration_seconds, request.mode, "req")
    result = gateway.execute(broker="fake", request_id="req", request=request, authorization=auth, admission=p117, safety=safety, snapshot=_snapshot())
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
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter)
    gateway = _gateway(registry, ExecutionLedger(tmp_path / "ledger.json"))
    auth = RealExecutionAuthorization("a", "audit", "fake", "adapter", False, False)
    admission = RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=False,
        authorization_active=False, safety_ready=False, broker_available=True, broker_id="fake",
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=False, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    result = gateway.execute(broker="fake", request_id="blocked", request=_request(), authorization=auth, admission=admission, safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.BLOCKED; assert adapter.calls == 0


def test_real_unknown_is_persisted_and_retry_is_blocked(tmp_path: Path):
    registry = BrokerRegistry(); adapter = UnknownAdapter(); registry.register("fake", adapter)
    ledger = ExecutionLedger(tmp_path / "ledger.json"); gateway = _gateway(registry, ledger)
    auth = _authorization(); admission = _admission(auth); safety = _safety(auth)
    request = _request()
    request = type(request)(request.symbol, request.signal, request.amount, request.duration_seconds, request.mode, "unknown-1")
    first = gateway.execute(broker="fake", request_id="unknown-1", request=request, authorization=auth, admission=admission, safety=safety, snapshot=_snapshot())
    assert first.status == RealGatewayStatus.UNKNOWN
    assert ledger.status("unknown-1") is ExecutionLedgerStatus.UNKNOWN
    restored = _gateway(registry, ExecutionLedger(tmp_path / "ledger.json"))
    second = restored.execute(broker="fake", request_id="unknown-1", request=request, authorization=auth, admission=admission, safety=safety, snapshot=_snapshot())
    assert second.status == RealGatewayStatus.UNKNOWN


def test_real_unknown_requires_explicit_reconciliation_before_resolution(tmp_path: Path):
    registry = BrokerRegistry(); registry.register("fake", UnknownAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json"); gateway = _gateway(registry, ledger)
    auth = _authorization(); admission = _admission(auth); safety = _safety(auth)
    request = _request()
    request = type(request)(request.symbol, request.signal, request.amount, request.duration_seconds, request.mode, "unknown-2")
    result = gateway.execute(broker="fake", request_id="unknown-2", request=request, authorization=auth, admission=admission, safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.UNKNOWN
    gateway.reconcile_unknown("unknown-2", executed=True)
    assert ledger.status("unknown-2") is ExecutionLedgerStatus.RECONCILED_EXECUTED


def test_real_reserved_after_restart_is_unknown_and_reconcilable(tmp_path: Path):
    path = tmp_path / "ledger.json"; ExecutionLedger(path).reserve("crashed")
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter)
    gateway = _gateway(registry, ExecutionLedger(path)); auth = _authorization(); admission = _admission(auth); safety = _safety(auth)
    request = _request()
    request = type(request)(request.symbol, request.signal, request.amount, request.duration_seconds, request.mode, "crashed")
    result = gateway.execute(broker="fake", request_id="crashed", request=request, authorization=auth, admission=admission, safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.UNKNOWN; assert adapter.calls == 0
    gateway.reconcile_unknown("crashed", executed=False)
    assert ExecutionLedger(path).status("crashed") is ExecutionLedgerStatus.RECONCILED_NOT_EXECUTED


def test_real_ledger_prevents_stale_instance_duplicate_reservation(tmp_path: Path):
    path = tmp_path / "ledger.json"; first = ExecutionLedger(path); second = ExecutionLedger(path); first.reserve("same-id")
    try:
        second.reserve("same-id")
    except ValueError:
        pass
    else:
        raise AssertionError("stale ledger must not reserve the same REAL request_id")


def test_real_gateway_rejects_malformed_request(tmp_path: Path):
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter)
    gateway = _gateway(registry, ExecutionLedger(tmp_path / "ledger.json")); auth = _authorization(); admission = _admission(auth); safety = _safety(auth)
    malformed = ExecutionRequest("TEST", Signal.COMPRA, float("nan"), 60, ExecutionMode.REAL)
    result = gateway.execute(broker="fake", request_id="bad", request=malformed, authorization=auth, admission=admission, safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.REJECTED; assert adapter.calls == 0


def test_real_gateway_rejects_mismatched_request_identity(tmp_path: Path):
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter)
    gateway = _gateway(registry, ExecutionLedger(tmp_path / "ledger.json")); auth = _authorization(); admission = _admission(auth); safety = _safety(auth)
    request = _request()
    request = type(request)(request.symbol, request.signal, request.amount, request.duration_seconds, request.mode, "request-owned-id")
    result = gateway.execute(
        broker="fake", request_id="gateway-owned-id", request=request,
        authorization=auth, admission=admission, safety=safety, snapshot=_snapshot(),
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0
    assert gateway._ledger.status("gateway-owned-id") is None


def test_real_accepted_without_external_id_is_unknown(tmp_path: Path):
    registry = BrokerRegistry(); registry.register("fake", NoExternalIdAdapter())
    ledger = ExecutionLedger(tmp_path / "ledger.json"); gateway = _gateway(registry, ledger); auth = _authorization(); admission = _admission(auth); safety = _safety(auth)
    request = _request()
    request = type(request)(request.symbol, request.signal, request.amount, request.duration_seconds, request.mode, "missing-id")
    result = gateway.execute(broker="fake", request_id="missing-id", request=request, authorization=auth, admission=admission, safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.UNKNOWN; assert ledger.status("missing-id") is ExecutionLedgerStatus.UNKNOWN


def test_real_gateway_blocks_changed_authoritative_risk_before_dispatch(tmp_path: Path):
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter)
    state = _risk_state(); provider = FakeRiskStateProvider(state); auth = _authorization(); safety = _safety(auth)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), provider, FakeRealSafetyProvider(safety))
    provider.state = OperationalState(
        balance=state.balance, equity=state.equity, realized_pnl=state.realized_pnl,
        unrealized_pnl=state.unrealized_pnl, trades_today=state.trades_today + 1,
        consecutive_losses=state.consecutive_losses, open_positions=state.open_positions,
        net_position=state.net_position, exposure=state.exposure, market_open=state.market_open,
    )
    result = gateway.execute(broker="fake", request_id="risk-changed", request=_request(), authorization=auth, admission=_admission(auth), safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.BLOCKED; assert adapter.calls == 0


def test_real_gateway_blocks_provider_failure_without_leaking_detail(tmp_path: Path):
    class BrokenProvider:
        def current_risk_state(self): raise RuntimeError("SECRET_RISK_PROVIDER_DETAIL")
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter); auth = _authorization(); safety = _safety(auth)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), BrokenProvider(), FakeRealSafetyProvider(safety))
    result = gateway.execute(broker="fake", request_id="risk-provider-fails", request=_request(), authorization=auth, admission=_admission(auth), safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.UNKNOWN
    assert "SECRET_RISK_PROVIDER_DETAIL" not in result.message; assert "RuntimeError" in result.message; assert adapter.calls == 0


def test_real_gateway_blocks_stale_safety_before_dispatch(tmp_path: Path):
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter); auth = _authorization(); admitted_safety = _safety(auth)
    provider = FakeRealSafetyProvider(admitted_safety)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), FakeRiskStateProvider(_risk_state()), provider)
    provider.report = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=False, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    result = gateway.execute(broker="fake", request_id="safety-changed", request=_request(), authorization=auth, admission=_admission(auth), safety=admitted_safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.BLOCKED; assert adapter.calls == 0


def test_real_gateway_blocks_safety_provider_failure_without_leaking_detail(tmp_path: Path):
    class BrokenSafetyProvider:
        def current_real_safety(self): raise RuntimeError("SECRET_SAFETY_PROVIDER_DETAIL")
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter); auth = _authorization(); safety = _safety(auth)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), FakeRiskStateProvider(_risk_state()), BrokenSafetyProvider())
    result = gateway.execute(broker="fake", request_id="safety-provider-fails", request=_request(), authorization=auth, admission=_admission(auth), safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.UNKNOWN
    assert "SECRET_SAFETY_PROVIDER_DETAIL" not in result.message; assert "RuntimeError" in result.message; assert adapter.calls == 0
