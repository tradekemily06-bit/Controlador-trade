from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RealExecutionAuthorization:
    authorization_id: str
    audit_id: str
    broker_id: str
    adapter_id: str
    explicitly_enabled: bool = False
    real_execution_allowed: bool = False

    def __post_init__(self) -> None:
        for name in ("authorization_id", "audit_id", "broker_id", "adapter_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if self.real_execution_allowed and not self.explicitly_enabled:
            raise ValueError("REAL exige habilitação explícita.")

    @property
    def active(self) -> bool:
        return self.explicitly_enabled and self.real_execution_allowed
