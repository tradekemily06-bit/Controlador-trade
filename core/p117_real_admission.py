from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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

    def __post_init__(self) -> None:
        for name in ("admission_id", "audit_id", "broker_id", "adapter_id", "request_id", "symbol"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if not isinstance(self.status, RealAdmissionStatus):
            raise TypeError("status de admissão REAL inválido.")
        if not isinstance(self.reasons, tuple) or not all(isinstance(reason, str) for reason in self.reasons):
            raise TypeError("reasons da admissão REAL deve ser uma tupla de strings.")

    @property
    def admitted(self) -> bool:
        return self.status is RealAdmissionStatus.ADMITTED


class RealAdmissionBoundary:
    def admit(self, *, admission_id: str, audit_id: str, audit_verified: bool,
              authorization_active: bool, safety_ready: bool,
              broker_available: bool, broker_id: str, adapter_id: str,
              request_id: str, symbol: str) -> RealAdmission:
        for name, value in (
            ("admission_id", admission_id), ("audit_id", audit_id),
            ("broker_id", broker_id), ("adapter_id", adapter_id),
            ("request_id", request_id), ("symbol", symbol),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")

        for name, value in (
            ("audit_verified", audit_verified),
            ("authorization_active", authorization_active),
            ("safety_ready", safety_ready),
            ("broker_available", broker_available),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} deve ser booleano.")

        reasons = []
        for ok, label in (
            (audit_verified, "auditoria P116 não verificada"),
            (authorization_active, "autorização REAL não ativa"),
            (safety_ready, "segurança REAL não pronta"),
            (broker_available, "corretora indisponível"),
        ):
            if not ok:
                reasons.append(label)
        status = RealAdmissionStatus.ADMITTED if not reasons else RealAdmissionStatus.BLOCKED
        return RealAdmission(
            admission_id, audit_id, status, broker_id, adapter_id,
            request_id, symbol, tuple(reasons),
        )
