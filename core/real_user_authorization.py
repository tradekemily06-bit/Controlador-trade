from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.ecosystem_state_store import EcosystemStateStore


@dataclass(frozen=True)
class RealUserAuthorization:
    authorization_id: str
    audit_id: str
    enabled: bool
    updated_at: str
    source: str = "ecosystem"

    @classmethod
    def disabled(cls) -> "RealUserAuthorization":
        return cls("real-disabled", "real-disabled", False, datetime.now(timezone.utc).isoformat())

    @classmethod
    def enable(cls) -> "RealUserAuthorization":
        stamp = datetime.now(timezone.utc).isoformat()
        return cls(f"real-user-{uuid4().hex}", f"real-audit-{uuid4().hex}", True, stamp)

    def active(self) -> bool:
        return self.enabled


class RealUserAuthorizationStore:
    """Durable user-controlled REAL authorization; never grants broker safety by itself."""

    KEY = "real_user_authorization"

    def __init__(self, path: str | Path) -> None:
        self.store = EcosystemStateStore(path)

    def load(self) -> RealUserAuthorization:
        value = self.store.load(self.KEY)
        if not isinstance(value, dict):
            return RealUserAuthorization.disabled()
        try:
            return RealUserAuthorization(
                authorization_id=str(value["authorization_id"]),
                audit_id=str(value["audit_id"]),
                enabled=bool(value["enabled"]),
                updated_at=str(value["updated_at"]),
                source=str(value.get("source", "ecosystem")),
            )
        except (KeyError, TypeError, ValueError):
            return RealUserAuthorization.disabled()

    def enable(self) -> RealUserAuthorization:
        value = RealUserAuthorization.enable()
        self.store.save(self.KEY, asdict(value))
        return value

    def disable(self) -> RealUserAuthorization:
        value = RealUserAuthorization.disabled()
        self.store.save(self.KEY, asdict(value))
        return value
