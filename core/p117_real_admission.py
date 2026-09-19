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
