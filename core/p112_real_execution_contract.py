from __future__ import annotations

from dataclasses import dataclass


_REAL_AUTHORIZATION_ISSUER_TOKEN = object()


@dataclass(frozen=True)
class RealExecutionAuthorization:
    """Immutable authorization bound to one exact REAL operation.

    An active authorization can only be constructed by the trusted issuer
    boundary. Inactive values remain constructible for safe negative/testing
    paths, but they can never authorize REAL dispatch.
    """

    authorization_id: str
    audit_id: str
    broker_id: str
    adapter_id: str
    request_id: str
    symbol: str
    explicitly_enabled: bool = False
    real_execution_allowed: bool = False
    _issuer_token: object | None = None

    def __post_init__(self) -> None:
        for name in (
            "authorization_id", "audit_id", "broker_id", "adapter_id",
            "request_id", "symbol",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if self.real_execution_allowed and not self.explicitly_enabled:
            raise ValueError("REAL exige habilitação explícita.")
        if self.active and self._issuer_token is not _REAL_AUTHORIZATION_ISSUER_TOKEN:
            raise PermissionError("autorização REAL ativa só pode ser emitida pela autoridade REAL autorizada.")

    @classmethod
    def _issue(
        cls, *, authorization_id: str, audit_id: str, broker_id: str,
        adapter_id: str, request_id: str, symbol: str,
    ) -> "RealExecutionAuthorization":
        return cls(
            authorization_id, audit_id, broker_id, adapter_id, request_id, symbol,
            True, True, _REAL_AUTHORIZATION_ISSUER_TOKEN,
        )

    @property
    def active(self) -> bool:
        return self.explicitly_enabled and self.real_execution_allowed
