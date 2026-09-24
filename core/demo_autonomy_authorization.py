from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DemoAutonomyAuthorization:
    """Durable, DEMO-only authorization for automatic operation.

    This authority is intentionally separate from user-facing preferences.
    It defaults to disabled and can never authorize REAL execution.
    """

    enabled: bool = False
    amount: float | None = None
    duration_seconds: int | None = None
    authorized_at: str | None = None
    authorized_by: str | None = None


class DemoAutonomyAuthorizationStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._state = self._load()

    @property
    def state(self) -> DemoAutonomyAuthorization:
        return self._state

    def enable(self, *, amount: float, duration_seconds: int, authorized_at: str, authorized_by: str) -> DemoAutonomyAuthorization:
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("amount deve ser positivo")
        if not isinstance(duration_seconds, int) or isinstance(duration_seconds, bool) or duration_seconds <= 0:
            raise ValueError("duration_seconds deve ser inteiro positivo")
        if not isinstance(authorized_at, str) or not authorized_at.strip():
            raise ValueError("authorized_at é obrigatório")
        if not isinstance(authorized_by, str) or not authorized_by.strip():
            raise ValueError("authorized_by é obrigatório")
        self._state = DemoAutonomyAuthorization(
            enabled=True,
            amount=float(amount),
            duration_seconds=duration_seconds,
            authorized_at=authorized_at.strip(),
            authorized_by=authorized_by.strip(),
        )
        self._save()
        return self._state

    def disable(self) -> DemoAutonomyAuthorization:
        self._state = DemoAutonomyAuthorization()
        self._save()
        return self._state

    def _load(self) -> DemoAutonomyAuthorization:
        if not self.path.exists():
            return DemoAutonomyAuthorization()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            state = DemoAutonomyAuthorization(**payload)
            self._validate(state)
            return state
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            # Corrupt authority state fails closed.
            return DemoAutonomyAuthorization()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(self._state.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    @staticmethod
    def _validate(state: DemoAutonomyAuthorization) -> None:
        if not isinstance(state.enabled, bool):
            raise ValueError("enabled inválido")
        if not state.enabled:
            return
        if state.amount is None or state.amount <= 0:
            raise ValueError("amount inválido")
        if state.duration_seconds is None or state.duration_seconds <= 0:
            raise ValueError("duration_seconds inválido")
        if not isinstance(state.authorized_at, str) or not state.authorized_at.strip():
            raise ValueError("authorized_at inválido")
        if not isinstance(state.authorized_by, str) or not state.authorized_by.strip():
            raise ValueError("authorized_by inválido")
