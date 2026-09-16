from __future__ import annotations

from dataclasses import dataclass


_REAL_AUTHORIZATION_ISSUER_TOKEN = object()
_REAL_AUTHORIZATION_ISSUER_CAPABILITY = object()


@dataclass(frozen=True, slots=True)
class _RealAuthorizationProof:
    identity: tuple[str, ...]
    _token: object

    def __post_init__(self) -> None:
        if self._token is not _REAL_AUTHORIZATION_ISSUER_TOKEN:
            raise PermissionError("prova de emissão REAL inválida.")


@dataclass(frozen=True, slots=True)
class RealExecutionAuthorization:
    """Immutable authorization bound to one exact REAL operation.

    Active authorization is issued only by the trusted issuer boundary. The
    private immutable proof is bound to every privileged identity field, so a
    copied, mutated or reconstructed object cannot remain active after its
    identity changes.
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
        if self.active and not self.issuer_valid:
            raise PermissionError("autorização REAL ativa só pode ser emitida pela autoridade REAL autorizada.")

    @classmethod
    def _issue(
        cls, *, authorization_id: str, audit_id: str, broker_id: str,
        adapter_id: str, request_id: str, symbol: str,
        issuer_capability: object,
    ) -> "RealExecutionAuthorization":
        if issuer_capability is not _REAL_AUTHORIZATION_ISSUER_CAPABILITY:
            raise PermissionError("emissão de autorização REAL exige a capacidade privada do emissor autorizado.")
        identity = (authorization_id, audit_id, broker_id, adapter_id, request_id, symbol)
        proof = _RealAuthorizationProof(identity, _REAL_AUTHORIZATION_ISSUER_TOKEN)
        return cls(
            authorization_id, audit_id, broker_id, adapter_id, request_id, symbol,
            True, True, proof,
        )

    @property
    def issuer_valid(self) -> bool:
        expected = (self.authorization_id, self.audit_id, self.broker_id,
                    self.adapter_id, self.request_id, self.symbol)
        return (isinstance(self._issuer_token, _RealAuthorizationProof)
                and self._issuer_token.identity == expected
                and self._issuer_token._token is _REAL_AUTHORIZATION_ISSUER_TOKEN)

    @property
    def active(self) -> bool:
        return self.explicitly_enabled and self.real_execution_allowed and self.issuer_valid
