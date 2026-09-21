from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from typing import Callable
from threading import RLock


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
        """Backward-compatible self-view for persisted state consumers."""
        return self

    def allows_execution(self) -> bool:
        return not self.enabled


class KillSwitch:
    """Safety gate independent from broker or execution adapter."""

    def __init__(self, on_change: Callable[[KillSwitchState], None] | None = None, change_fence: Callable[[], object] | None = None) -> None:
        if on_change is not None and not callable(on_change):
            raise ValueError("on_change deve ser chamável ou None.")
        self._state = KillSwitchState()
        self._lock = RLock()
        if change_fence is not None and not callable(change_fence):
            raise ValueError("change_fence deve ser chamável ou None.")
        self._on_change = on_change
        self._change_fence = change_fence

    @property
    def state(self) -> KillSwitchState:
        with self._lock:
            return self._state

    def set_on_change(self, callback: Callable[[KillSwitchState], None] | None) -> None:
        """Attach persistence/observation after trusted state restoration."""
        if callback is not None and not callable(callback):
            raise ValueError("callback deve ser chamável ou None.")
        with self._lock:
            self._on_change = callback

    def set_change_fence(self, change_fence: Callable[[], object] | None) -> None:
        """Attach the same cross-process fence used by operational dispatch."""
        if change_fence is not None and not callable(change_fence):
            raise ValueError("change_fence deve ser chamável ou None.")
        with self._lock:
            self._change_fence = change_fence

    def _commit(self, state: KillSwitchState) -> KillSwitchState:
        with self._lock:
            fence_provider = self._change_fence
            callback = self._on_change
            context = fence_provider() if fence_provider is not None else nullcontext()
            with context:
                self._state = state
                if callback is not None:
                    callback(state)
                return state

    def activate(self, reason: str) -> KillSwitchState:
        return self._commit(KillSwitchState(enabled=True, reason=reason))

    def deactivate(self) -> KillSwitchState:
        return self._commit(KillSwitchState(enabled=False, reason=None))

    def synchronize(self, state: KillSwitchState) -> KillSwitchState:
        """Adopt trusted persisted state without invoking persistence callbacks."""
        if not isinstance(state, KillSwitchState):
            raise KillSwitchValidationError("state deve ser KillSwitchState.")
        with self._lock:
            self._state = state
            return state

    def allows_execution(self) -> bool:
        with self._lock:
            return not self._state.enabled

    def guard(self) -> None:
        with self._lock:
            state = self._state
            if state.enabled:
                raise RuntimeError(f"execução bloqueada pelo kill switch: {state.reason}")
