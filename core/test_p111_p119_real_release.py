from pathlib import Path

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.global_operational_barrier import GlobalOperationalBarrier, SafetyComponent
from core.models import Signal
from core.operational_state import OperationalState
from core.p111_pre_real_audit import PreRealAuditBoundary, PreRealAuditStatus
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate, RealSafetyReport, RealSafetyState
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary, ReleaseAuditStatus
from core.p117_real_admission import RealAdmissionBoundary, RealAdmissionStatus
from core.p118_real_monitoring import RealMonitoringBoundary, RealOutcomeStatus
from core.p119_release_closure import RealReleaseClosureBoundary, RealReleaseState
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.risk_state_fingerprint import risk_state_identity
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger, ExecutionLedgerStatus
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class FakeAdapter:
    def __init__(self, result=None, error=False, available=True):
        self.result = result or ExecutionResult(True, "accepted", "external-1")
        self.error = error
        self.available = available
        self.calls = 0

    def is_available(self):
        return self.available

    def execute(self, request):
        self.calls += 1
        if self.error:
            raise TimeoutError("timeout after dispatch")
        return self.result


class NoExternalIdAdapter(FakeAdapter):
    def __init__(self):
        super().__init__(ExecutionResult(True, "accepted but reference missing", None))


class UnknownAdapter(FakeAdapter):
    def __init__(self):
        super().__init__(error=True)


class FakeRiskStateProvider:
    def __init__(self, state): self.state = state
    def current_risk_state(self): return self.state


class FakeRealSafetyProvider:
    def __init__(self, report): self.report = report
    def current_real_safety(self): return self.report


def _risk_state():
    return OperationalState(balance=1000.0, equity=1000.0, realized_pnl=0.0, unrealized_pnl=0.0,
                            trades_today=0, consecutive_losses=0, open_positions=0,
                            net_position=0.0, exposure=0.0, market_open=True)


def _snapshot(state=None):
    state = state or _risk_state()
    return DecisionSnapshot(signal="COMPRA", analysis_score=90.0, confirmed=True, quality_score=90.0,
                            quality_level="HIGH", actionable=True, decision="COMPRA", decision_reason="test",
                            market_context=None, market_direction=None, market_score=None,
                            operational_state_available=True, trades_today=state.trades_today,
                            consecutive_losses=state.consecutive_losses, symbol="TEST", timeframe="5m",
                            risk_state_identity=risk_state_identity(state))


def _authorization(request_id="req-1", symbol="TEST", broker_id="fake", adapter_id="fake-adapter"):
    audit = RealReleaseAuditBoundary().audit(
        audit_id="a116", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    return RealAuthorizationIssuer().issue(
        audit=audit, authorization_id="auth", audit_id="a116", broker_id=broker_id,
        adapter_id=adapter_id, request_id=request_id, symbol=symbol, explicit_approval=True,
    )


def _safety(auth=None):
    return RealSafetyGate().evaluate(authorization_active=True if auth is None else auth.active,
                                     kill_switch_clear=True, market_healthy=True, recovery_safe=True,
                                     risk_approved=True, broker_available=True)


def _admission(request_id="req-1", symbol="TEST", broker_id="fake", adapter_id="fake-adapter", auth=None, audit_id="a116"):
    admission_auth = auth if auth is not None and auth.active else _authorization(
        request_id=request_id, symbol=symbol, broker_id=broker_id, adapter_id=adapter_id
    )
    audit = RealReleaseAuditBoundary().audit(
        audit_id=audit_id, pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id=audit_id, audit_verified=audit,
        authorization_active=admission_auth, safety_ready=True, broker_available=True,
        broker_id=broker_id, adapter_id=adapter_id, request_id=request_id, symbol=symbol,
    )

def _request(request_id="req-1", symbol="TEST", state=None):
    state = state or _risk_state()
    return ExecutionRequest(symbol, Signal.COMPRA, 10.0, 60, ExecutionMode.REAL,
                            request_id=request_id, risk_state_fingerprint=risk_state_identity(state))


def _gateway(registry, ledger, barrier=None):
    state = _risk_state(); safety = _safety()
    return RealExecutionGateway(BrokerAdapterGateway(registry), ledger, FakeRiskStateProvider(state),
                                FakeRealSafetyProvider(safety),
                                operational_barrier_provider=lambda: barrier if barrier is not None else GlobalOperationalBarrier())


def test_p111_p116_p117_p119_positive_flow(tmp_path: Path):
    p111 = PreRealAuditBoundary().audit(audit_id="a111", p110_decision="VALIDATED", safety_verified=True,
                                        risk_verified=True, gateway_present=True, broker_boundary_present=True)
    assert p111.status is PreRealAuditStatus.VERIFIED
    shadow = ShadowValidationBoundary().validate(validation_id="shadow", adapter_available=True, real_safety_ready=True,
                                                 duplicate_blocked=True, kill_switch_blocked=True, real_mode_rejected_by_shadow=True)
    assert shadow.passed
    safety = _safety(); assert safety.state is RealSafetyState.READY
    p116 = RealReleaseAuditBoundary().audit(audit_id="a116", pre_real_verified=p111.verified,
                                             shadow_passed=shadow.passed, safety_ready=safety.ready,
                                             broker_boundary_ready=True, explicit_real_contract=True)
    assert p116.status is ReleaseAuditStatus.VERIFIED
    auth = RealAuthorizationIssuer().issue(
        audit=p116, authorization_id="auth", audit_id="a116", broker_id="fake",
        adapter_id="fake-adapter", request_id="req-1", symbol="TEST", explicit_approval=True,
    )
    assert auth.active
    safety = _safety(auth)
    p117 = _admission(auth=auth); assert p117.status is RealAdmissionStatus.ADMITTED
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "real-ledger.json"); gateway = _gateway(registry, ledger)
    result = gateway.execute(broker="fake", request_id="req-1", request=_request(), authorization=auth,
                             admission=p117, safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.ADMITTED and adapter.calls == 1
    assert ledger.status("req-1") is ExecutionLedgerStatus.ACCEPTED
    observation = RealMonitoringBoundary().observe(observation_id="obs", request_id="req-1", result=result.execution)
    assert observation.status is RealOutcomeStatus.ACCEPTED
    p119 = RealReleaseClosureBoundary().close(release_id="release", p116_verified=p116.verified,
                                               p117_admitted=p117.admitted, p118_available=True, multi_broker_boundary=True)
    assert p119.state is RealReleaseState.RELEASED


def test_real_authorization_rejects_fabricated_verified_audit():
    from core.p116_real_release_audit import RealReleaseAudit
    fabricated = RealReleaseAudit("forged", ReleaseAuditStatus.VERIFIED, ("P111", "P112", "P113", "P114", "P115"), ())
    with pytest.raises(ValueError, match="fronteira"):
        RealAuthorizationIssuer().issue(
            audit=fabricated, authorization_id="auth", audit_id="forged", broker_id="fake",
            adapter_id="fake-adapter", request_id="req", symbol="TEST", explicit_approval=True,
        )


def test_real_authorization_is_explicit():
    inactive = RealExecutionAuthorization("a", "audit", "broker", "adapter", "req", "TEST", False, False)
    assert not inactive.active
    with pytest.raises(ValueError):
        RealExecutionAuthorization("a", "audit", "broker", "adapter", "req", "TEST", False, True)


def test_real_safety_fails_closed():
    report = RealSafetyGate().evaluate(authorization_active=True, kill_switch_clear=False, market_healthy=True,
                                       recovery_safe=True, risk_approved=True, broker_available=True)
    assert report.state is RealSafetyState.BLOCKED


def test_real_gateway_blocks_without_active_authorization(tmp_path: Path):
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter")
    gateway = _gateway(registry, ExecutionLedger(tmp_path / "ledger.json"))
    auth = RealExecutionAuthorization("a", "audit", "fake", "fake-adapter", "blocked", "TEST", False, False)
    admission = _admission("blocked", auth=auth); safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="blocked", request=_request("blocked"), authorization=auth,
                             admission=admission, safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.BLOCKED and adapter.calls == 0


def test_real_unknown_is_persisted_and_retry_is_blocked(tmp_path: Path):
    registry = BrokerRegistry(); adapter = UnknownAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); gateway = _gateway(registry, ledger)
    auth = _authorization("unknown-1"); admission = _admission("unknown-1", auth=auth); safety = _safety(auth)
    request = _request("unknown-1")
    first = gateway.execute(broker="fake", request_id="unknown-1", request=request, authorization=auth, admission=admission, safety=safety, snapshot=_snapshot())
    assert first.status == RealGatewayStatus.UNKNOWN and ledger.status("unknown-1") is ExecutionLedgerStatus.UNKNOWN
    restored = _gateway(registry, ExecutionLedger(tmp_path / "ledger.json"))
    second = restored.execute(broker="fake", request_id="unknown-1", request=request, authorization=auth, admission=admission, safety=safety, snapshot=_snapshot())
    assert second.status == RealGatewayStatus.UNKNOWN and adapter.calls == 1


def test_real_unknown_requires_explicit_reconciliation_before_resolution(tmp_path: Path):
    gateway = _gateway(BrokerRegistry(), ExecutionLedger(tmp_path / "ledger.json"))
    with pytest.raises(RuntimeError, match="evidência externa"):
        gateway.reconcile_unknown("missing", executed=True)


def test_real_reserved_after_restart_is_unknown_and_reconcilable(tmp_path: Path):
    path = tmp_path / "ledger.json"; ExecutionLedger(path).reserve("crashed")
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter")
    gateway = _gateway(registry, ExecutionLedger(path)); auth = _authorization("crashed"); safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="crashed", request=_request("crashed"), authorization=auth,
                             admission=_admission("crashed", auth=auth), safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.UNKNOWN and adapter.calls == 0


def test_real_ledger_prevents_stale_instance_duplicate_reservation(tmp_path: Path):
    path = tmp_path / "ledger.json"; first = ExecutionLedger(path); second = ExecutionLedger(path); first.reserve("same-id")
    with pytest.raises(ValueError): second.reserve("same-id")


def test_real_gateway_rejects_malformed_request(tmp_path: Path):
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter")
    gateway = _gateway(registry, ExecutionLedger(tmp_path / "ledger.json")); auth = _authorization("bad"); safety = _safety(auth)
    malformed = ExecutionRequest("TEST", Signal.COMPRA, float("nan"), 60, ExecutionMode.REAL, request_id="bad", risk_state_fingerprint=risk_state_identity(_risk_state()))
    result = gateway.execute(broker="fake", request_id="bad", request=malformed, authorization=auth,
                             admission=_admission("bad", auth=auth), safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.REJECTED and adapter.calls == 0


def test_real_gateway_rejects_mismatched_request_identity(tmp_path: Path):
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter")
    gateway = _gateway(registry, ExecutionLedger(tmp_path / "ledger.json")); auth = _authorization("request-owned-id"); safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="gateway-owned-id", request=_request("request-owned-id"), authorization=auth,
                             admission=_admission("request-owned-id", auth=auth), safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.BLOCKED and adapter.calls == 0


def test_real_accepted_without_external_id_is_unknown(tmp_path: Path):
    registry = BrokerRegistry(); registry.register("fake", NoExternalIdAdapter(), adapter_id="fake-adapter")
    ledger = ExecutionLedger(tmp_path / "ledger.json"); gateway = _gateway(registry, ledger); auth = _authorization("missing-id"); safety = _safety(auth)
    result = gateway.execute(broker="fake", request_id="missing-id", request=_request("missing-id"), authorization=auth,
                             admission=_admission("missing-id", auth=auth), safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.UNKNOWN and ledger.status("missing-id") is ExecutionLedgerStatus.UNKNOWN


def test_real_gateway_blocks_changed_authoritative_risk_before_dispatch(tmp_path: Path):
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter")
    state = _risk_state(); provider = FakeRiskStateProvider(state); auth = _authorization("risk-changed"); safety = _safety(auth)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), provider,
                                   FakeRealSafetyProvider(safety), operational_barrier_provider=lambda: GlobalOperationalBarrier())
    provider.state = OperationalState(balance=state.balance, equity=state.equity, realized_pnl=state.realized_pnl,
                                      unrealized_pnl=state.unrealized_pnl, trades_today=1,
                                      consecutive_losses=state.consecutive_losses, open_positions=state.open_positions,
                                      net_position=state.net_position, exposure=state.exposure, market_open=state.market_open)
    result = gateway.execute(broker="fake", request_id="risk-changed", request=_request("risk-changed"), authorization=auth,
                             admission=_admission("risk-changed", auth=auth), safety=safety, snapshot=_snapshot(state))
    assert result.status == RealGatewayStatus.BLOCKED and adapter.calls == 0


def test_real_gateway_blocks_provider_failure_without_leaking_detail(tmp_path: Path):
    class BrokenProvider:
        def current_risk_state(self): raise RuntimeError("SECRET_RISK_PROVIDER_DETAIL")
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter"); auth = _authorization("risk-provider-fails"); safety = _safety(auth)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), BrokenProvider(),
                                   FakeRealSafetyProvider(safety), operational_barrier_provider=lambda: GlobalOperationalBarrier())
    result = gateway.execute(broker="fake", request_id="risk-provider-fails", request=_request("risk-provider-fails"), authorization=auth,
                             admission=_admission("risk-provider-fails", auth=auth), safety=safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.UNKNOWN and "SECRET_RISK_PROVIDER_DETAIL" not in result.message


def test_real_gateway_blocks_stale_safety_before_dispatch(tmp_path: Path):
    registry = BrokerRegistry(); adapter = FakeAdapter(); registry.register("fake", adapter, adapter_id="fake-adapter"); auth = _authorization("safety-changed"); admitted_safety = _safety(auth)
    provider = FakeRealSafetyProvider(admitted_safety)
    gateway = RealExecutionGateway(BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), FakeRiskStateProvider(_risk_state()), provider,
                                   operational_barrier_provider=lambda: GlobalOperationalBarrier())
    provider.report = RealSafetyGate().evaluate(authorization_active=True, kill_switch_clear=False, market_healthy=True,
                                                recovery_safe=True, risk_approved=True, broker_available=True)
    result = gateway.execute(broker="fake", request_id="safety-changed", request=_request("safety-changed"), authorization=auth,
                             admission=_admission("safety-changed", auth=auth), safety=admitted_safety, snapshot=_snapshot())
    assert result.status == RealGatewayStatus.BLOCKED and adapter.calls == 0
