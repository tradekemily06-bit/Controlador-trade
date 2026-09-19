from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class RealExecutionAuthorization:
    """Explicit REAL authorization bound to one broker/account/session."""

    authorization_id: str
    audit_id: str
    broker_id: str
    adapter_id: str
    explicitly_enabled: bool = False
    real_execution_allowed: bool = False
    account_id: str | None = None
    session_id: str | None = None
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=5))

    def __post_init__(self) -> None:
        for name in ("authorization_id", "audit_id", "broker_id", "adapter_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        for name in ("account_id", "session_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} inválido.")
        for name in ("issued_at", "expires_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} deve ser timezone-aware.")
        now = datetime.now(timezone.utc)
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at deve ser posterior a issued_at.")
        if self.issued_at > now + timedelta(seconds=30):
            raise ValueError("issued_at não pode estar significativamente no futuro.")
        if self.expires_at - self.issued_at > timedelta(minutes=5):
            raise ValueError("autorização REAL não pode exceder 5 minutos.")
        if self.real_execution_allowed and not self.explicitly_enabled:
            raise ValueError("REAL exige habilitação explícita.")

    @property
    def active(self) -> bool:
        return (
            self.explicitly_enabled
            and self.real_execution_allowed
            and bool(self.account_id)
            and bool(self.session_id)
            and datetime.now(timezone.utc) < self.expires_at
        )
