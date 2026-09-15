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


class KillSwitch:
    """Safety gate independent from broker or execution adapter.

    An optional change callback lets the runtime persist safety state. The
    callback is invoked only after a validated state transition; it cannot
    authorize execution and persistence failures are allowed to surface.
    """

    def __init__(self, on_change: Callable[[KillSwitchState], None] | None = None) -> None:
        if on_change is not None and not callable(on_change):
            raise ValueError("on_change deve ser chamável ou None.")
        self._state = KillSwitchState()
        self._on_change = on_change

    @property
    def state(self) -> KillSwitchState:
        return self._state

    def _commit(self, state: KillSwitchState) -> KillSwitchState:
        self._state = state
        if self._on_change is not None:
            self._on_change(state)
        return state

    def activate(self, reason: str) -> KillSwitchState:
        return self._commit(KillSwitchState(enabled=True, reason=reason))

    def deactivate(self) -> KillSwitchState:
        return self._commit(KillSwitchState(enabled=False, reason=None))

    def allows_execution(self) -> bool:
        return not self._state.enabled

    def guard(self) -> None:
        if self._state.enabled:
            raise RuntimeError(f"execução bloqueada pelo kill switch: {self._state.reason}")
