from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

_REAL_ADMISSION_ISSUER_TOKEN = object()
_REAL_ADMISSION_ISSUER_CAPABILITY = object()


@dataclass(frozen=True, slots=True)
class _RealAdmissionProof:
    identity: tuple[object, ...]
    _token: object

    def __post_init__(self) -> None:
        if self._token is not _REAL_ADMISSION_ISSUER_TOKEN:
            raise PermissionError("prova de emissão de admissão REAL inválida.")


class RealAdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RealAdmission:
    """Immutable admission bound to the exact operation and adapter."""

    admission_id: str
    audit_id: str
    status: RealAdmissionStatus
    broker_id: str
    adapter_id: str
    request_id: str
    symbol: str
    reasons: tuple[str, ...]
    _issuer_token: object | None = None

    def __post_init__(self) -> None:
        for name in ("admission_id", "audit_id", "broker_id", "adapter_id", "request_id", "symbol"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if not isinstance(self.status, RealAdmissionStatus):
            raise TypeError("status de admissão REAL inválido.")
        if not isinstance(self.reasons, tuple) or not all(isinstance(reason, str) for reason in self.reasons):
            raise TypeError("reasons da admissão REAL deve ser uma tupla de strings.")
        if self.admitted and not self.issuer_valid:
            raise PermissionError("admissão REAL ativa só pode ser emitida pela autoridade REAL autorizada.")

    @property
    def admitted(self) -> bool:
        return self.status is RealAdmissionStatus.ADMITTED and self.issuer_valid

    @property
    def issuer_valid(self) -> bool:
        expected = (self.admission_id, self.audit_id, self.status.value,
                    self.broker_id, self.adapter_id, self.request_id,
                    self.symbol, self.reasons)
        return (isinstance(self._issuer_token, _RealAdmissionProof)
                and self._issuer_token.identity == expected
                and self._issuer_token._token is _REAL_ADMISSION_ISSUER_TOKEN)


class RealAdmissionBoundary:
    def _issue(self, *, admission_id: str, audit_id: str,
               audit_verified: bool, authorization: object,
               safety_ready: bool, broker_available: bool,
               issuer_capability: object) -> RealAdmission:
        from core.p112_real_execution_contract import RealExecutionAuthorization

        if issuer_capability is not _REAL_ADMISSION_ISSUER_CAPABILITY:
            raise PermissionError("emissão de admissão REAL exige a capacidade privada do emissor autorizado.")
        if not isinstance(authorization, RealExecutionAuthorization) or not authorization.active or not authorization.issuer_valid:
            raise PermissionError("autorização REAL ativa e emitida pela autoridade são obrigatórias para emitir admissão.")
        broker_id = authorization.broker_id
        adapter_id = authorization.adapter_id
        request_id = authorization.request_id
        symbol = authorization.symbol
        if not all(isinstance(value, str) and value.strip() for value in (
            admission_id, audit_id, broker_id, adapter_id, request_id, symbol,
        )):
            raise ValueError("identidade da admissão REAL incompleta.")
        reasons = []
        for ok, label in (
            (audit_verified, "auditoria P116 não verificada"),
            (authorization.active, "autorização REAL não ativa"),
            (safety_ready, "segurança REAL não pronta"),
            (broker_available, "corretora indisponível"),
        ):
            if not isinstance(ok, bool):
                raise TypeError("estado da admissão REAL inválido.")
            if not ok:
                reasons.append(label)
        status = RealAdmissionStatus.ADMITTED if not reasons else RealAdmissionStatus.BLOCKED
        proof = None
        if status is RealAdmissionStatus.ADMITTED:
            identity = (admission_id, audit_id, status.value, broker_id,
                        adapter_id, request_id, symbol, tuple(reasons))
            proof = _RealAdmissionProof(identity, _REAL_ADMISSION_ISSUER_TOKEN)
        return RealAdmission(
            admission_id, audit_id, status, broker_id, adapter_id,
            request_id, symbol, tuple(reasons), proof,
        )

    def admit(self, *, admission_id: str, audit_id: str, audit_verified: bool,
              authorization_active: bool, safety_ready: bool,
              broker_available: bool, broker_id: str, adapter_id: str,
              request_id: str, symbol: str) -> RealAdmission:
        """Legacy/public entry point: it may only create BLOCKED state."""
        for name, value in (
            ("admission_id", admission_id), ("audit_id", audit_id),
            ("broker_id", broker_id), ("adapter_id", adapter_id),
            ("request_id", request_id), ("symbol", symbol),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        for name, value in (
            ("audit_verified", audit_verified), ("authorization_active", authorization_active),
            ("safety_ready", safety_ready), ("broker_available", broker_available),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} deve ser booleano.")
        reasons = []
        for ok, label in (
            (audit_verified, "auditoria P116 não verificada"),
            (authorization_active, "autorização REAL não ativa; emissor autorizado obrigatório"),
            (safety_ready, "segurança REAL não pronta"),
            (broker_available, "corretora indisponível"),
        ):
            if not ok:
                reasons.append(label)
        if not reasons:
            reasons.append("emissão de admissão REAL exige RealPrivilegeIssuer")
        return RealAdmission(
            admission_id, audit_id, RealAdmissionStatus.BLOCKED,
            broker_id, adapter_id, request_id, symbol, tuple(reasons),
        )
