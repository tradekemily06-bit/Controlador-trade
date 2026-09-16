from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.global_operational_barrier import GlobalOperationalBarrier
from core.models import Signal
from core.operational_state import OperationalState
from core.p111_pre_real_audit import PreRealAuditBoundary
from core.p114_real_safety_gate import RealSafetyGate
from core.p115_shadow_validation import ShadowValidationBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.real_privilege_issuer import RealPrivilegeIssuer
from core.real_safety_provider import RealSafetyProvider
from core.risk_state_fingerprint import risk_state_identity
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus


class Adapter:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "accepted", "external-risk-test")


class Provider:
    def __init__(self, state):
        self.state = state

    def current_risk_state(self):
        return self.state


class SafetyProvider(RealSafetyProvider):
    def current_real_safety(self):
        return RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True, market_healthy=True,
            recovery_safe=True, risk_approved=True, broker_available=True,
        )


def state():
    return OperationalState(
        balance=1000.0, equity=1000.0, realized_pnl=0.0,
        unrealized_pnl=0.0, trades_today=0, consecutive_losses=0,
        open_positions=0, net_position=0.0, exposure=0.0,
        market_open=True, last_processed_candle=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )


def snapshot(s):
    return DecisionSnapshot(
        signal="COMPRA", analysis_score=90.0, confirmed=True,
        quality_score=90.0, quality_level="HIGH", actionable=True,
        decision="COMPRA", decision_reason="test", market_context=None,
        market_direction=None, market_score=None, operational_state_available=True,
        trades_today=s.trades_today, consecutive_losses=s.consecutive_losses,
        symbol="TEST", timeframe="5m", risk_state_identity=risk_state_identity(s),
    )


def _release_audit():
    p111 = PreRealAuditBoundary().audit(
        audit_id="a111", p110_decision="VALIDATED", safety_verified=True,
        risk_verified=True, gateway_present=True, broker_boundary_present=True,
    )
    shadow = ShadowValidationBoundary().validate(
        validation_id="shadow", adapter_available=True, real_safety_ready=True,
        duplicate_blocked=True, kill_switch_blocked=True, real_mode_rejected_by_shadow=True,
    )
    safety = RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True,
        recovery_safe=True, risk_approved=True, broker_available=True,
    )
    return RealReleaseAuditBoundary().audit(
        audit_id="a116", pre_real_verified=p111.verified,
        shadow_passed=shadow.passed, safety_ready=safety.ready,
        broker_boundary_ready=True, explicit_real_contract=True,
    )


def _authorization(request_id):
    registry = BrokerRegistry()
    registry.register("fake", Adapter(), adapter_id="fake-adapter")
    request = ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id=request_id)
    return RealPrivilegeIssuer(BrokerAdapterGateway(registry)).issue_authorization(
        authorization_id=f"auth-{request_id}", release_audit=_release_audit(), broker="fake",
        request=request, explicit_real_enablement=True,
    )


def _admission(auth):
    registry = BrokerRegistry()
    registry.register("fake", Adapter(), adapter_id="fake-adapter")
    return RealPrivilegeIssuer(BrokerAdapterGateway(registry)).issue_admission(
        admission_id=f"adm-{auth.request_id}", authorization=auth, release_audit=_release_audit(),
        safety=RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True, market_healthy=True,
            recovery_safe=True, risk_approved=True, broker_available=True,
        ), broker_available=True,
    )


def gateway(tmp_path: Path, provider: Provider, adapter: Adapter):
    registry = BrokerRegistry()
    registry.register("fake", adapter, adapter_id="fake-adapter")
    return RealExecutionGateway(
        BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"),
        provider, SafetyProvider(),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )


def request(request_id):
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id=request_id)


@pytest.mark.parametrize(
    "field, value",
    [
        ("balance", 999.0), ("equity", 999.0), ("realized_pnl", -1.0),
        ("unrealized_pnl", 1.0), ("trades_today", 1), ("consecutive_losses", 1),
        ("open_positions", 1), ("net_position", 1.0), ("exposure", 100.0),
        ("market_open", False),
        ("last_processed_candle", datetime(2026, 9, 15, 0, 1, tzinfo=timezone.utc)),
    ],
)
def test_real_blocks_every_changed_risk_field(tmp_path: Path, field, value):
    original = state()
    provider = Provider(original)
    adapter = Adapter()
    gateway_instance = gateway(tmp_path, provider, adapter)
    changed_values = {name: getattr(original, name) for name in original.__dataclass_fields__}
    changed_values[field] = value
    provider.state = OperationalState(**changed_values)
    request_id = f"risk-{field}"
    auth = _authorization(request_id)
    req = request(request_id)
    result = gateway_instance.execute(
        broker="fake", request_id=request_id, request=req,
        authorization=auth, admission=_admission(auth),
        safety=RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True, market_healthy=True,
            recovery_safe=True, risk_approved=True, broker_available=True,
        ), snapshot=snapshot(original),
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_allows_unchanged_authoritative_risk_state(tmp_path: Path):
    original = state(); provider = Provider(original); adapter = Adapter()
    gateway_instance = gateway(tmp_path, provider, adapter)
    auth = _authorization("risk-unchanged"); req = request("risk-unchanged")
    result = gateway_instance.execute(
        broker="fake", request_id=req.request_id, request=req,
        authorization=auth, admission=_admission(auth),
        safety=RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True, market_healthy=True,
            recovery_safe=True, risk_approved=True, broker_available=True,
        ), snapshot=snapshot(original),
    )
    assert result.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1


def test_real_blocks_missing_decision_risk_identity(tmp_path: Path):
    original = state(); provider = Provider(original); adapter = Adapter()
    gateway_instance = gateway(tmp_path, provider, adapter)
    base = snapshot(original)
    snapshot_without_identity = DecisionSnapshot(**{**base.as_dict(), "risk_state_identity": None})
    auth = _authorization("risk-no-identity"); req = request("risk-no-identity")
    result = gateway_instance.execute(
        broker="fake", request_id=req.request_id, request=req,
        authorization=auth, admission=_admission(auth),
        safety=RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True, market_healthy=True,
            recovery_safe=True, risk_approved=True, broker_available=True,
        ), snapshot=snapshot_without_identity,
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_provider_failure_is_fail_closed_and_sanitized(tmp_path: Path):
    class BrokenProvider:
        def current_risk_state(self):
            raise RuntimeError("SECRET_PROVIDER_DETAILS")
    original = state(); adapter = Adapter()
    gateway_instance = gateway(tmp_path, BrokenProvider(), adapter)
    auth = _authorization("risk-provider-error"); req = request("risk-provider-error")
    result = gateway_instance.execute(
        broker="fake", request_id=req.request_id, request=req,
        authorization=auth, admission=_admission(auth),
        safety=RealSafetyGate().evaluate(
            authorization_active=True, kill_switch_clear=True, market_healthy=True,
            recovery_safe=True, risk_approved=True, broker_available=True,
        ), snapshot=snapshot(original),
    )
    assert result.status == RealGatewayStatus.UNKNOWN
    assert "SECRET_PROVIDER_DETAILS" not in result.message
    assert "RuntimeError" in result.message
    assert adapter.calls == 0
