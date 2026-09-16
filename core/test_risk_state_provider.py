from __future__ import annotations

import pytest

from core.operational_state import OperationalState
from core.risk_state_provider import RiskStateProvider, read_authoritative_risk_state


class Provider:
    def __init__(self, state: OperationalState) -> None:
        self.state = state

    def current_risk_state(self) -> OperationalState:
        return self.state


def test_provider_contract_returns_current_operational_state() -> None:
    state = OperationalState(balance=1000.0, equity=990.0, exposure=25.0)
    provider = Provider(state)

    assert isinstance(provider, RiskStateProvider)
    assert read_authoritative_risk_state(provider) is state


def test_provider_rejects_invalid_result() -> None:
    class BadProvider:
        def current_risk_state(self):
            return {"trades_today": 0}

    assert isinstance(BadProvider(), RiskStateProvider)
    with pytest.raises(TypeError, match="invalid state"):
        read_authoritative_risk_state(BadProvider())


def test_provider_rejects_non_provider() -> None:
    with pytest.raises(TypeError, match="required contract"):
        read_authoritative_risk_state(object())
