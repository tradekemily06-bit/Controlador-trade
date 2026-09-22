from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from typing import Iterator


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

    The execution guard closes the in-process race between the final safety
    check and external dispatch. Cross-process coordination still belongs to
    the durable execution boundary.
    """

    def __init__(self) -> None:
        self._state = KillSwitchState()
        self._execution_lock = RLock()

    @property
    def state(self) -> KillSwitchState:
        with self._execution_lock:
            return self._state

    def activate(self, reason: str) -> KillSwitchState:
        with self._execution_lock:
            self._state = KillSwitchState(enabled=True, reason=reason)
            return self._state

    def deactivate(self) -> KillSwitchState:
        with self._execution_lock:
            self._state = KillSwitchState(enabled=False, reason=None)
            return self._state

    def allows_execution(self) -> bool:
        with self._execution_lock:
            return not self._state.enabled

    @contextmanager
    def execution_guard(self) -> Iterator[None]:
        """Serialize kill-switch changes with a critical dispatch section."""
        with self._execution_lock:
            yield

    def guard(self) -> None:
        with self._execution_lock:
            if self._state.enabled:
                raise RuntimeError(f"execução bloqueada pelo kill switch: {self._state.reason}")
