from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import threading


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
    """Safety gate independent from broker or execution adapter."""

    def __init__(self) -> None:
        self._state = KillSwitchState()
        self._lock = threading.RLock()

    @property
    def state(self) -> KillSwitchState:
        with self._lock:
            return self._state

    def activate(self, reason: str) -> KillSwitchState:
        with self._lock:
            self._state = KillSwitchState(enabled=True, reason=reason)
            return self._state

    def deactivate(self) -> KillSwitchState:
        with self._lock:
            self._state = KillSwitchState(enabled=False, reason=None)
            return self._state

    def allows_execution(self) -> bool:
        with self._lock:
            return not self._state.enabled

    @contextmanager
    def execution_window(self):
        """Atomically check the switch and cross the executor admission boundary.

        The lock is intentionally held only across the final safety check and the
        executor call. A kill-switch activation racing this window waits until
        the current admission has crossed the external side-effect boundary;
        subsequent admissions are then blocked. This does not pretend to cancel
        an order that has already been handed to an executor.
        """
        with self._lock:
            yield self

    def guard(self) -> None:
        with self._lock:
            if self._state.enabled:
                raise RuntimeError(f"execução bloqueada pelo kill switch: {self._state.reason}")
