import pytest

from core.p114_real_safety_gate import RealSafetyGate
from core.real_safety_provider import RealSafetyProvider, read_authoritative_real_safety


class Provider:
    def current_real_safety(self):
        return RealSafetyGate().evaluate(
            authorization_active=True,
            kill_switch_clear=True,
            market_healthy=True,
            recovery_safe=True,
            risk_approved=True,
            broker_available=True,
        )


def test_real_safety_provider_contract_is_runtime_checkable():
    assert isinstance(Provider(), RealSafetyProvider)
    assert read_authoritative_real_safety(Provider()).ready


def test_real_safety_provider_rejects_invalid_report():
    class InvalidProvider:
        def current_real_safety(self):
            return {"ready": True}

    with pytest.raises(TypeError):
        read_authoritative_real_safety(InvalidProvider())


def test_real_safety_provider_never_falls_back_on_provider_failure():
    class BrokenProvider:
        def current_real_safety(self):
            raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError):
        read_authoritative_real_safety(BrokenProvider())


def test_real_safety_gate_rejects_non_boolean_prerequisite():
    with pytest.raises(TypeError):
        RealSafetyGate().evaluate(
            authorization_active=True,
            kill_switch_clear=1,
            market_healthy=True,
            recovery_safe=True,
            risk_approved=True,
            broker_available=True,
        )
