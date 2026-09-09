from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PreRealAuditStatus(str, Enum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PreRealAudit:
    audit_id: str
    status: PreRealAuditStatus
    checks: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return self.status is PreRealAuditStatus.VERIFIED


class PreRealAuditBoundary:
    """Factual, fail-closed gate for the transition toward REAL capability."""

    def audit(self, *, audit_id: str, p110_decision: str, safety_verified: bool,
              risk_verified: bool, gateway_present: bool,
              broker_boundary_present: bool) -> PreRealAudit:
        if not isinstance(audit_id, str) or not audit_id.strip():
            raise ValueError("audit_id é obrigatório.")
        checks = (
            "P110 decision available",
            "safety boundary verified",
            "risk boundary verified",
            "execution gateway present",
            "broker boundary present",
        )
        reasons: list[str] = []
        if p110_decision not in {"VALIDATED", "REJECTED", "INCONCLUSIVE"}:
            reasons.append("decisão P110 inválida")
        if p110_decision != "VALIDATED":
            reasons.append("P110 não está VALIDATED")
        if not safety_verified:
            reasons.append("segurança não verificada")
        if not risk_verified:
            reasons.append("risco não verificado")
        if not gateway_present:
            reasons.append("gateway de execução ausente")
        if not broker_boundary_present:
            reasons.append("fronteira de corretora ausente")
        status = PreRealAuditStatus.VERIFIED if not reasons else PreRealAuditStatus.BLOCKED
        return PreRealAudit(audit_id, status, checks, tuple(reasons))
