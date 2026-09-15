from datetime import datetime, timezone

from core.decision_freshness import DecisionFreshnessPolicy
from core.decision_snapshot import DecisionSnapshot
from core.global_operational_barrier import GlobalOperationalBarrier
from core.kill_switch import KillSwitch
from core.models import Signal
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.ports import ExecutionMode, ExecutionRequest
from execution.paper import PaperExecutor

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
RISK_A = "a" * 64
RISK_B = "b" * 64


def request(risk=None):
    return ExecutionRequest("EURUSD", Signal.COMPRA, 10.0, 60, ExecutionMode.DEMO, risk_state_fingerprint=risk)


def snapshot(risk=None):
    return DecisionSnapshot("COMPRA", 90.0, True, 90.0, "FORTE", True, "EXECUTAR", "validada", "FAVORAVEL", "ALTA", 90.0, True, 0, 0, "EURUSD", "5m", risk)


def gateway(provider=None):
    return ExecutionGateway(
        PaperExecutor(), KillSwitch(),
        operational_barrier_provider=lambda: GlobalOperationalBarrier(),
        decision_freshness_policy=DecisionFreshnessPolicy(max_age_seconds=30),
        decision_clock=lambda: NOW,
        risk_state_fingerprint_provider=provider,
    )


def test_risk_identity_requires_authoritative_provider():
    result = gateway().execute("risk-required", request(RISK_A), snapshot=snapshot(RISK_A), timestamp=NOW)
    assert result.status is GatewayStatus.BLOCKED


def test_risk_identity_blocks_mismatch():
    result = gateway(lambda: RISK_B).execute("risk-mismatch", request(RISK_A), snapshot=snapshot(RISK_A), timestamp=NOW)
    assert result.status is GatewayStatus.BLOCKED
    assert "mudou" in result.message


def test_risk_identity_blocks_provider_failure():
    def fail():
        raise RuntimeError("unavailable")
    result = gateway(fail).execute("risk-failure", request(RISK_A), snapshot=snapshot(RISK_A), timestamp=NOW)
    assert result.status is GatewayStatus.BLOCKED
    assert "indisponível" in result.message


def test_risk_identity_is_rechecked_before_dispatch():
    calls = []
    def changing_provider():
        calls.append(True)
        return RISK_A if len(calls) == 1 else RISK_B
    result = gateway(changing_provider).execute("risk-race", request(RISK_A), snapshot=snapshot(RISK_A), timestamp=NOW)
    assert result.status is GatewayStatus.BLOCKED
    assert len(calls) >= 2
    assert "mudou" in result.message
