from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX fallback
    msvcrt = None


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
    """Fail-closed kill switch with optional durable cross-process coordination.

    When state_path and coordination_path are supplied, every read of the
    execution decision reloads the durable state and activation/deactivation
    uses the same coordination lock as REAL dispatch. This makes a kill-switch
    activation atomic with respect to the REAL dispatch critical section on a
    shared filesystem. Without those paths the object retains its lightweight
    in-memory semantics for isolated DEMO/unit-test use.
    """

    def __init__(self, *, state_path: str | Path | None = None,
                 coordination_path: str | Path | None = None) -> None:
        self._state = KillSwitchState()
        self._state_path = Path(state_path).expanduser().resolve() if state_path is not None else None
        self._coordination_path = Path(coordination_path).expanduser().resolve() if coordination_path is not None else None
        if self._state_path is not None:
            self._load_durable()

    @property
    def state(self) -> KillSwitchState:
        if self._state_path is not None:
            self._load_durable()
        return self._state

    @contextmanager
    def _coordination(self):
        if self._coordination_path is None:
            yield
            return
        lock_path = self._coordination_path.with_name(
            f".{self._coordination_path.name}.coordination.lock"
        )
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            elif msvcrt is not None:
                lock_file.seek(0, 2)
                if lock_file.tell() == 0:
                    lock_file.write(b"0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:  # pragma: no cover
                raise RuntimeError("plataforma sem mecanismo de lock suportado.")
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                else:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)

    def _load_durable(self) -> None:
        assert self._state_path is not None
        if not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            self._state = KillSwitchState(
                enabled=payload.get("enabled", False),
                reason=payload.get("reason"),
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            # A corrupted safety state must never silently become CLEAR.
            self._state = KillSwitchState(enabled=True, reason="estado persistido do kill switch inválido")
            raise KillSwitchValidationError("estado persistido do kill switch inválido.") from exc

    def _write_durable(self, state: KillSwitchState) -> None:
        assert self._state_path is not None
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_path.with_name(f".{self._state_path.name}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump({"enabled": state.enabled, "reason": state.reason}, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self._state_path)
        if os.name != "nt":
            with self._state_path.open("rb") as handle:
                os.fsync(handle.fileno())
            directory_fd = os.open(self._state_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

    def activate(self, reason: str) -> KillSwitchState:
        state = KillSwitchState(enabled=True, reason=reason)
        with self._coordination():
            if self._state_path is not None:
                self._load_durable()
                self._write_durable(state)
            self._state = state
        return state

    def deactivate(self) -> KillSwitchState:
        state = KillSwitchState(enabled=False, reason=None)
        with self._coordination():
            if self._state_path is not None:
                self._load_durable()
                self._write_durable(state)
            self._state = state
        return state

    def allows_execution(self) -> bool:
        if self._state_path is not None:
            try:
                self._load_durable()
            except KillSwitchValidationError:
                return False
        return not self._state.enabled

    def guard(self) -> None:
        if not self.allows_execution():
            raise RuntimeError(f"execução bloqueada pelo kill switch: {self._state.reason}")
