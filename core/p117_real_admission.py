from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

_REAL_ADMISSION_ISSUER_TOKEN = object()


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
        if self.admitted and self._issuer_token is not _REAL_ADMISSION_ISSUER_TOKEN:
            raise PermissionError("admissão REAL ativa só pode ser emitida pela autoridade REAL autorizada.")

    @property
    def admitted(self) -> bool:
        return self.status is RealAdmissionStatus.ADMITTED


class RealAdmissionBoundary:
    def _issue(self, *, admission_id: str, audit_id: str,
               audit_verified: bool, authorization: object,
               safety_ready: bool, broker_available: bool) -> RealAdmission:
        from core.p112_real_execution_contract import RealExecutionAuthorization

        if not isinstance(authorization, RealExecutionAuthorization) or not authorization.active:
            raise PermissionError("autorização REAL ativa é obrigatória para emitir admissão.")
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
        return RealAdmission(
            admission_id, audit_id, status, broker_id, adapter_id,
            request_id, symbol, tuple(reasons), _REAL_ADMISSION_ISSUER_TOKEN,
        )

    def admit(self, *, admission_id: str, audit_id: str, audit_verified: bool,
              authorization_active: bool, safety_ready: bool,
              broker_available: bool, broker_id: str, adapter_id: str,
              request_id: str, symbol: str) -> RealAdmission:
        """Legacy/public entry point: it may only create BLOCKED state.

        Active REAL admission must come from RealPrivilegeIssuer._issue(),
        which derives identity from an already-issued authorization.
        """
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
