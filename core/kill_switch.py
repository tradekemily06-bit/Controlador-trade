from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class KillSwitchValidationError(ValueError):
    """Raised when a kill-switch state is invalid."""


@dataclass(frozen=True)
class KillSwitchState:
    enabled: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise KillSwitchValidationError("enabled deve ser booleano.")
        if self.enabled and (self.reason is None or not self.reason.strip()):
            raise KillSwitchValidationError("kill switch ativo exige motivo.")
        if self.reason is not None and not isinstance(self.reason, str):
            raise KillSwitchValidationError("reason deve ser texto ou None.")

    @property
    def state(self) -> "KillSwitchState":
        """Compatibility projection for callers that treat loaded state as a gate."""
        return self

    def allows_execution(self) -> bool:
        return not self.enabled


class KillSwitch:
    """Safety gate independent from broker or execution adapter."""

    def __init__(self, on_change: Callable[[KillSwitchState], None] | None = None) -> None:
        if on_change is not None and not callable(on_change):
            raise ValueError("on_change deve ser chamável ou None.")
        self._state = KillSwitchState()
        self._on_change = on_change

    @property
    def state(self) -> KillSwitchState:
        return self._state

    def set_on_change(self, callback: Callable[[KillSwitchState], None] | None) -> None:
        """Attach persistence/observation after trusted state restoration."""
        if callback is not None and not callable(callback):
            raise ValueError("callback deve ser chamável ou None.")
        self._on_change = callback

    def _commit(self, state: KillSwitchState) -> KillSwitchState:
        self._state = state
        if self._on_change is not None:
            self._on_change(state)
        return state

    def activate(self, reason: str) -> KillSwitchState:
        return self._commit(KillSwitchState(enabled=True, reason=reason))

    def deactivate(self) -> KillSwitchState:
        return self._commit(KillSwitchState(enabled=False, reason=None))

    def synchronize(self, state: KillSwitchState) -> KillSwitchState:
        """Adopt trusted persisted state without invoking persistence callbacks.

        This is intentionally separate from activate/deactivate so a runtime
        can refresh a cross-process safety decision without rewriting the
        source of truth it just read.
        """
        if not isinstance(state, KillSwitchState):
            raise KillSwitchValidationError("state deve ser KillSwitchState.")
        self._state = state
        return state

    def allows_execution(self) -> bool:
        return not self._state.enabled

    def guard(self) -> None:
        if self._state.enabled:
            raise RuntimeError(f"execução bloqueada pelo kill switch: {self._state.reason}")
