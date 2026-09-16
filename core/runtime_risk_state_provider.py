"""Strict adapter for wiring an authoritative runtime risk-state source."""

from __future__ import annotations

from collections.abc import Callable

from core.operational_state import OperationalState


class RuntimeRiskStateProvider:
    """Expose an explicitly supplied authoritative runtime state getter.

    This adapter owns no state and performs no fallback. The caller must supply
    the actual runtime authority; returning a cached decision snapshot or a
    synthetic/default state is therefore a composition error, not something this
    class silently repairs.
    """

    def __init__(self, getter: Callable[[], OperationalState]) -> None:
        if not callable(getter):
            raise TypeError("getter must be callable")
        self._getter = getter

    def current_risk_state(self) -> OperationalState:
        state = self._getter()
        if not isinstance(state, OperationalState):
            raise TypeError("runtime risk-state getter returned an invalid state")
        return state
