from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from core.file_lock import exclusive_file_lock


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
    """Fail-safe kill switch, optionally backed by a shared durable state file.

    A path-backed instance is the REAL-process boundary: every read refreshes
    from durable state and every mutation is serialized with an inter-process
    lock. The default in-memory mode is retained for DEMO/unit-test callers.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._state = KillSwitchState()
        if self._path is not None:
            self._validate_path()
            self._load()

    def _validate_path(self) -> None:
        if self._path is None:
            return
        if self._path.name in ("", ".", ".."):
            raise KillSwitchValidationError("caminho do kill switch inválido.")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _lock_path(self) -> Path:
        assert self._path is not None
        return self._path.with_name(f".{self._path.name}.lock")

    @staticmethod
    def _decode(payload: object) -> KillSwitchState:
        if not isinstance(payload, dict):
            raise KillSwitchValidationError("estado persistido do kill switch inválido.")
        return KillSwitchState(
            enabled=payload.get("enabled", False),
            reason=payload.get("reason"),
        )

    def _load(self) -> KillSwitchState:
        if self._path is None:
            return self._state
        if not self._path.exists():
            self._state = KillSwitchState()
            return self._state
        try:
            payload = json.loads(
                self._path.read_text(encoding="utf-8"),
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"constante JSON não permitida: {value}")
                ),
            )
            self._state = self._decode(payload)
            return self._state
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            KillSwitchValidationError,
        ) as exc:
            raise KillSwitchValidationError(
                "estado persistido do kill switch inválido."
            ) from exc

    def _save_locked(self, state: KillSwitchState) -> KillSwitchState:
        assert self._path is not None
        temporary = self._path.with_name(f".{self._path.name}.tmp")
        temporary.write_text(
            json.dumps(
                {"enabled": state.enabled, "reason": state.reason},
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        try:
            with temporary.open("r+b") as durable_file:
                durable_file.flush()
                os.fsync(durable_file.fileno())
            os.replace(temporary, self._path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
        directory_fd = os.open(self._path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        self._state = state
        return state

    @property
    def state(self) -> KillSwitchState:
        if self._path is not None:
            return self._load()
        return self._state

    def activate(self, reason: str) -> KillSwitchState:
        state = KillSwitchState(enabled=True, reason=reason)
        if self._path is None:
            self._state = state
            return state
        try:
            with exclusive_file_lock(self._lock_path()):
                return self._save_locked(state)
        except OSError as exc:
            raise KillSwitchValidationError(
                f"não foi possível persistir o kill switch: {exc}"
            ) from exc

    def deactivate(self) -> KillSwitchState:
        state = KillSwitchState(enabled=False, reason=None)
        if self._path is None:
            self._state = state
            return state
        try:
            with exclusive_file_lock(self._lock_path()):
                return self._save_locked(state)
        except OSError as exc:
            raise KillSwitchValidationError(
                f"não foi possível persistir o kill switch: {exc}"
            ) from exc

    def allows_execution(self) -> bool:
        return not self.state.enabled

    def guard(self) -> None:
        state = self.state
        if state.enabled:
            raise RuntimeError(f"execução bloqueada pelo kill switch: {state.reason}")
