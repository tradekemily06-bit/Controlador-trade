from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.operational_state import OperationalState


@runtime_checkable
class RiskStateProvider(Protocol):
    """Authoritative runtime source for risk-relevant operational state.

    Implementations must return the current state from the runtime authority,
    not a decision-time cache. The execution boundary may use this contract to
    revalidate a decision immediately before dispatch.
    """

    def current_risk_state(self) -> OperationalState:
        """Return the freshest authoritative operational risk state."""
        ...


def read_authoritative_risk_state(provider: RiskStateProvider) -> OperationalState:
    """Read and validate the authoritative risk state without fail-open fallbacks."""
    if not isinstance(provider, RiskStateProvider):
        raise TypeError("risk state provider does not implement the required contract")
    state = provider.current_risk_state()
    if not isinstance(state, OperationalState):
        raise TypeError("risk state provider returned an invalid state")
    return state
