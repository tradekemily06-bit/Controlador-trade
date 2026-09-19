from __future__ import annotations

from dataclasses import dataclass


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

    def __post_init__(self) -> None:
        for name in ("authorization_id", "audit_id", "broker_id", "adapter_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        for name in ("account_id", "session_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} inválido.")
        if self.real_execution_allowed and not self.explicitly_enabled:
            raise ValueError("REAL exige habilitação explícita.")

    @property
    def active(self) -> bool:
        return (
            self.explicitly_enabled
            and self.real_execution_allowed
            and bool(self.account_id)
            and bool(self.session_id)
        )
