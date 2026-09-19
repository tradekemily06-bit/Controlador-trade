from __future__ import annotations

from dataclasses import dataclass


class KillSwitchValidationError(ValueError):
    """Raised when a kill-switch state is invalid."""


@dataclass(frozen=True)
class KillSwitchState:
    enabled: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise KillSwitchValidationError("enabled deve ser booleano.")
        if self.reason is not None and type(self.reason) is not str:
            raise KillSwitchValidationError("reason deve ser texto ou None.")
        if self.enabled and not self.reason.strip():
            raise KillSwitchValidationError("kill switch ativo exige motivo.")


class KillSwitch:
    """Safety gate independent from broker or execution adapter."""

    def __init__(self) -> None:
        self._state = KillSwitchState()

    @property
    def state(self) -> KillSwitchState:
        return self._state

    def activate(self, reason: str) -> KillSwitchState:
        self._state = KillSwitchState(enabled=True, reason=reason)
        return self._state

    def deactivate(self) -> KillSwitchState:
        self._state = KillSwitchState(enabled=False, reason=None)
        return self._state

    def allows_execution(self) -> bool:
        return not self._state.enabled

    def guard(self) -> None:
        if self._state.enabled:
            raise RuntimeError(f"execução bloqueada pelo kill switch: {self._state.reason}")
