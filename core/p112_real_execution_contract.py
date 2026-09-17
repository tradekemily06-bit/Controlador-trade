from __future__ import annotations

from dataclasses import dataclass, field
import weakref


class _AuthorizationProvenanceToken:
    """Private identity token proving issuance by the REAL authorization issuer."""


# A second, exact capability is required to enter the low-level factory. The
# factory remains in this contract module because it owns the immutable object,
# but callers must come through the dedicated issuer boundary. This is an
# in-process capability check; structural tests additionally ensure the helper
# is not called from another production module.
_AUTHORIZATION_ISSUER_CAPABILITY = object()
_AUTHORIZATION_PROVENANCE: dict[int, weakref.ReferenceType[_AuthorizationProvenanceToken]] = {}


@dataclass(frozen=True)
class RealExecutionAuthorization:
    """Immutable authorization bound to one exact REAL operation.

    An object is active only when it carries a private provenance token that was
    registered by the dedicated issuer. Field values alone therefore cannot
    manufacture REAL authority at runtime.
    """

    authorization_id: str
    audit_id: str
    broker_id: str
    adapter_id: str
    request_id: str
    symbol: str
    explicitly_enabled: bool = False
    real_execution_allowed: bool = False
    _provenance_token: _AuthorizationProvenanceToken | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        for name in (
            "authorization_id", "audit_id", "broker_id", "adapter_id",
            "request_id", "symbol",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if not isinstance(self.explicitly_enabled, bool) or not isinstance(self.real_execution_allowed, bool):
            raise ValueError("flags REAL inválidas.")
        if self.real_execution_allowed and not self.explicitly_enabled:
            raise ValueError("REAL exige habilitação explícita.")
        if self._provenance_token is not None and not isinstance(self._provenance_token, _AuthorizationProvenanceToken):
            raise TypeError("proveniência da autorização REAL inválida.")

    @property
    def active(self) -> bool:
        if not (self.explicitly_enabled and self.real_execution_allowed):
            return False
        token = self._provenance_token
        if token is None:
            return False
        reference = _AUTHORIZATION_PROVENANCE.get(id(token))
        return reference is not None and reference() is token


def _issue_real_authorization(
    *,
    authorization_id: str,
    audit_id: str,
    broker_id: str,
    adapter_id: str,
    request_id: str,
    symbol: str,
    issuer_capability: object,
) -> RealExecutionAuthorization:
    """Create the active contract only for the dedicated issuer boundary."""
    if issuer_capability is not _AUTHORIZATION_ISSUER_CAPABILITY:
        raise PermissionError("somente o emissor autorizado pode criar autoridade REAL ativa.")
    token = _AuthorizationProvenanceToken()
    authorization = RealExecutionAuthorization(
        authorization_id, audit_id, broker_id, adapter_id, request_id, symbol,
        True, True, token,
    )
    key = id(token)
    _AUTHORIZATION_PROVENANCE[key] = weakref.ref(
        token,
        lambda _reference, key=key: _AUTHORIZATION_PROVENANCE.pop(key, None),
    )
    return authorization
