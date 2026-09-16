import pytest

from core.p114_real_safety_gate import RealSafetyState
from core.runtime_real_safety_provider import RuntimeRealSafetyProvider


def _provider(values=None):
    values = values or {
        "authorization": True,
        "kill_switch": True,
        "market": True,
        "recovery": True,
        "risk": True,
        "broker": True,
    }
    return RuntimeRealSafetyProvider(
        authorization_active=lambda: values["authorization"],
        kill_switch_clear=lambda: values["kill_switch"],
        market_healthy=lambda: values["market"],
        recovery_safe=lambda: values["recovery"],
        risk_approved=lambda: values["risk"],
        broker_available=lambda: values["broker"],
    )


def test_runtime_provider_reads_live_sources_on_every_call():
    values = {"authorization": True, "kill_switch": True, "market": True, "recovery": True, "risk": True, "broker": True}
    provider = _provider(values)
    assert provider.current_real_safety().state is RealSafetyState.READY
    values["kill_switch"] = False
    report = provider.current_real_safety()
    assert report.state is RealSafetyState.BLOCKED
    assert "kill switch ativo" in report.reasons


def test_runtime_provider_requires_boolean_sources():
    provider = RuntimeRealSafetyProvider(
        authorization_active=lambda: True,
        kill_switch_clear=lambda: "true",
        market_healthy=lambda: True,
        recovery_safe=lambda: True,
        risk_approved=lambda: True,
        broker_available=lambda: True,
    )
    with pytest.raises(TypeError):
        provider.current_real_safety()


def test_runtime_provider_propagates_source_failure_without_fail_open():
    def broken():
        raise RuntimeError("SECRET_SAFETY_SOURCE")

    provider = RuntimeRealSafetyProvider(
        authorization_active=lambda: True,
        kill_switch_clear=broken,
        market_healthy=lambda: True,
        recovery_safe=lambda: True,
        risk_approved=lambda: True,
        broker_available=lambda: True,
    )
    with pytest.raises(RuntimeError):
        provider.current_real_safety()


def test_each_live_safety_source_can_block():
    names = ("authorization", "kill_switch", "market", "recovery", "risk", "broker")
    for name in names:
        values = {key: True for key in names}
        values[name] = False
        report = _provider(values).current_real_safety()
        assert report.state is RealSafetyState.BLOCKED
        assert report.reasons
