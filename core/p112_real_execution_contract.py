from __future__ import annotations

from dataclasses import dataclass


_ISSUANCE_TOKEN = object()


@dataclass(frozen=True)
class RealExecutionAuthorization:
    """Immutable authorization bound to one exact REAL operation.

    Active REAL authorization is issuer-controlled. Direct construction of an
    active privilege is intentionally rejected; use
    ``issue_real_execution_authorization`` after the upstream release/audit
    boundary has approved the operation.
    """

    authorization_id: str
    audit_id: str
    broker_id: str
    adapter_id: str
    request_id: str
    symbol: str
    explicitly_enabled: bool = False
    real_execution_allowed: bool = False
    _issuance_token: object | None = None

    def __post_init__(self) -> None:
        for name in (
            "authorization_id", "audit_id", "broker_id", "adapter_id",
            "request_id", "symbol",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if not isinstance(self.explicitly_enabled, bool) or not isinstance(self.real_execution_allowed, bool):
            raise TypeError("flags de habilitação REAL devem ser booleanos.")
        if self.real_execution_allowed and self._issuance_token is not _ISSUANCE_TOKEN:
            raise PermissionError("autorização REAL ativa só pode ser emitida pela fronteira de privilégio autorizada.")
        if self.real_execution_allowed and not self.explicitly_enabled:
            raise ValueError("REAL exige habilitação explícita.")
        object.__setattr__(self, "_issuance_token", None)

    @property
    def active(self) -> bool:
        return self.explicitly_enabled and self.real_execution_allowed


def issue_real_execution_authorization(
    *,
    authorization_id: str,
    audit_id: str,
    broker_id: str,
    adapter_id: str,
    request_id: str,
    symbol: str,
) -> RealExecutionAuthorization:
    """Authoritative issuance primitive for an active REAL authorization.

    This function is deliberately the only supported path that can create an
    active authorization. Upstream callers remain responsible for proving the
    audit/release prerequisites before invoking this primitive.
    """
    return RealExecutionAuthorization(
        authorization_id=authorization_id,
        audit_id=audit_id,
        broker_id=broker_id,
        adapter_id=adapter_id,
        request_id=request_id,
        symbol=symbol,
        explicitly_enabled=True,
        real_execution_allowed=True,
        _issuance_token=_ISSUANCE_TOKEN,
    )
