from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.decision_snapshot import DecisionSnapshot
from core.models import Signal
from core.operational_state import OperationalState
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from core.p116_real_release_audit import RealReleaseAuditBoundary
from core.real_authorization_issuer import RealAuthorizationIssuer
from core.risk_state_fingerprint import risk_state_identity
from core.global_operational_barrier import GlobalOperationalBarrier
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


def gateway(tmp_path: Path, provider: Provider, adapter: Adapter):
    registry = BrokerRegistry()
    registry.register("fake", adapter, adapter_id="adapter")
    safety_provider = type("SafetyProvider", (), {"current_real_safety": lambda self: RealSafetyGate().evaluate(
        authorization_active=True, kill_switch_clear=True, market_healthy=True, recovery_safe=True,
        risk_approved=True, broker_available=True,
    )})()
    return RealExecutionGateway(
        BrokerAdapterGateway(registry), ExecutionLedger(tmp_path / "ledger.json"), provider, safety_provider,
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
    )


def authorization(request_id="risk-unchanged"):
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit",
        pre_real_verified=True,
        shadow_passed=True,
        safety_ready=True,
        broker_boundary_ready=True,
        explicit_real_contract=True,
    )
    return RealAuthorizationIssuer().issue(
        audit=audit,
        authorization_id="auth",
        audit_id="audit",
        broker_id="fake",
        adapter_id="adapter",
        request_id=request_id,
        symbol="TEST",
        explicit_approval=True,
    )


def admission(auth):
    audit = RealReleaseAuditBoundary().audit(
        audit_id="audit", pre_real_verified=True, shadow_passed=True,
        safety_ready=True, broker_boundary_ready=True, explicit_real_contract=True,
    )
    return RealAdmissionBoundary().admit(
        admission_id="adm", audit_id="audit", audit_verified=audit,
        authorization_active=auth, safety_ready=True, broker_available=True,
        broker_id="fake", adapter_id="adapter", request_id=auth.request_id, symbol=auth.symbol,
    )


def safety(auth):
    return RealSafetyGate().evaluate(
        authorization_active=auth.active, kill_switch_clear=True,
        market_healthy=True, recovery_safe=True, risk_approved=True,
        broker_available=True,
    )


def request(request_id="risk-unchanged"):
    return ExecutionRequest("TEST", Signal.COMPRA, 10.0, 60, ExecutionMode.REAL, request_id=request_id, risk_state_fingerprint=risk_state_identity(state()))


@pytest.mark.parametrize(
    "field, value",
    [
        ("balance", 999.0),
        ("equity", 999.0),
        ("realized_pnl", -1.0),
        ("unrealized_pnl", 1.0),
        ("trades_today", 1),
        ("consecutive_losses", 1),
        ("open_positions", 1),
        ("net_position", 1.0),
        ("exposure", 100.0),
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
    auth = authorization(f"risk-{field}")

    result = gateway_instance.execute(
        broker="fake", request_id=f"risk-{field}", request=request(f"risk-{field}"),
        authorization=auth, admission=admission(auth), safety=safety(auth),
        snapshot=snapshot(original),
    )

    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_allows_unchanged_authoritative_risk_state(tmp_path: Path):
    original = state()
    provider = Provider(original)
    adapter = Adapter()
    gateway_instance = gateway(tmp_path, provider, adapter)
    auth = authorization("risk-unchanged")
    result = gateway_instance.execute(
        broker="fake", request_id="risk-unchanged", request=request("risk-unchanged"),
        authorization=auth, admission=admission(auth), safety=safety(auth),
        snapshot=snapshot(original),
    )
    assert result.status == RealGatewayStatus.ADMITTED
    assert adapter.calls == 1


def test_real_blocks_missing_decision_risk_identity(tmp_path: Path):
    original = state()
    provider = Provider(original)
    adapter = Adapter()
    gateway_instance = gateway(tmp_path, provider, adapter)
    base = snapshot(original)
    snapshot_without_identity = replace(base, risk_state_fingerprint=None, risk_state_identity=None)
    auth = authorization("risk-no-identity")
    result = gateway_instance.execute(
        broker="fake", request_id="risk-no-identity", request=request("risk-no-identity"),
        authorization=auth, admission=admission(auth), safety=safety(auth),
        snapshot=snapshot_without_identity,
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_blocks_request_risk_identity_mismatch(tmp_path: Path):
    original = state()
    provider = Provider(original)
    adapter = Adapter()
    gateway_instance = gateway(tmp_path, provider, adapter)
    auth = authorization("risk-request-mismatch")
    stale_request = replace(
        request("risk-request-mismatch"),
        risk_state_fingerprint="stale-risk-identity",
    )
    result = gateway_instance.execute(
        broker="fake", request_id="risk-request-mismatch", request=stale_request,
        authorization=auth, admission=admission(auth), safety=safety(auth),
        snapshot=snapshot(original),
    )
    assert result.status == RealGatewayStatus.BLOCKED
    assert "identidade de risco da requisição difere do snapshot" in result.message
    assert adapter.calls == 0


def test_real_provider_failure_is_fail_closed_and_sanitized(tmp_path: Path):
    class BrokenProvider:
        def current_risk_state(self):
            raise RuntimeError("SECRET_PROVIDER_DETAILS")

    original = state()
    adapter = Adapter()
    gateway_instance = gateway(tmp_path, BrokenProvider(), adapter)
    auth = authorization("risk-provider-error")
    result = gateway_instance.execute(
        broker="fake", request_id="risk-provider-error", request=request("risk-provider-error"),
        authorization=auth, admission=admission(auth), safety=safety(auth),
        snapshot=snapshot(original),
    )
    assert result.status == RealGatewayStatus.UNKNOWN
    assert "SECRET_PROVIDER_DETAILS" not in result.message
    assert "RuntimeError" in result.message
    assert adapter.calls == 0
