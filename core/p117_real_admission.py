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
        if not admission_id.strip() or not audit_id.strip() or not broker_id.strip():
            raise ValueError("identificadores e broker_id são obrigatórios.")
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
        return RealAdmission(admission_id, audit_id, status, broker_id, tuple(reasons))
