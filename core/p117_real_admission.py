from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RealAdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RealAdmission:
    admission_id: str
    audit_id: str
    status: RealAdmissionStatus
    broker_id: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("admission_id", "audit_id", "broker_id"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip() or value != value.strip():
                raise ValueError(f"{name} inválido.")
        if not isinstance(self.status, RealAdmissionStatus):
            raise ValueError("status de admissão REAL inválido.")
        if not isinstance(self.reasons, tuple) or any(
            type(reason) is not str or not reason.strip() for reason in self.reasons
        ):
            raise ValueError("reasons da admissão REAL inválidos.")
        if self.status is RealAdmissionStatus.ADMITTED and self.reasons:
            raise ValueError("admissão REAL ADMITTED não pode carregar motivos de bloqueio.")
        if self.status is RealAdmissionStatus.BLOCKED and not self.reasons:
            raise ValueError("admissão REAL BLOCKED precisa registrar o motivo do bloqueio.")

    @property
    def admitted(self) -> bool:
        return self.status is RealAdmissionStatus.ADMITTED


class RealAdmissionBoundary:
    def admit(self, *, admission_id: str, audit_id: str, audit_verified: bool,
              authorization_active: bool, safety_ready: bool,
              broker_available: bool, broker_id: str) -> RealAdmission:
        for name, value in (
            ("admission_id", admission_id),
            ("audit_id", audit_id),
            ("broker_id", broker_id),
        ):
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        for value in (audit_verified, authorization_active, safety_ready, broker_available):
            if type(value) is not bool:
                raise ValueError("pré-requisitos de admissão REAL precisam ser booleanos.")
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
        return RealAdmission(admission_id.strip(), audit_id.strip(), status, broker_id.strip(), tuple(reasons))
