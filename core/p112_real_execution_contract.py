from __future__ import annotations

from dataclasses import dataclass, field


# Module-private capability used only by RealAuthorizationIssuer. The public
# constructor can represent an inactive contract, but cannot create an active
# authorization by itself.
_ISSUER_CAPABILITY = object()


@dataclass(frozen=True)
class RealExecutionAuthorization:
    """Immutable authorization bound to one exact REAL operation."""

    authorization_id: str
    audit_id: str
    broker_id: str
    adapter_id: str
    request_id: str
    symbol: str
    explicitly_enabled: bool = False
    real_execution_allowed: bool = False
    _issuer_capability: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in (
            "authorization_id", "audit_id", "broker_id", "adapter_id",
            "request_id", "symbol",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if not isinstance(self.explicitly_enabled, bool) or not isinstance(self.real_execution_allowed, bool):
            raise TypeError("flags de autorização REAL devem ser booleanos.")
        if self.real_execution_allowed and not self.explicitly_enabled:
            raise ValueError("REAL exige habilitação explícita.")
        if self._issuer_capability is not _ISSUER_CAPABILITY and (self.explicitly_enabled or self.real_execution_allowed):
            raise ValueError("autorização REAL ativa só pode ser emitida pela autoridade de autorização controlada.")

    @property
    def active(self) -> bool:
        return (
            self.explicitly_enabled
            and self.real_execution_allowed
            and self._issuer_capability is _ISSUER_CAPABILITY
        )
