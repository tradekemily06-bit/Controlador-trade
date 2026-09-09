from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReleaseAuditStatus(str, Enum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RealReleaseAudit:
    audit_id: str
    status: ReleaseAuditStatus
    prerequisites: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return self.status is ReleaseAuditStatus.VERIFIED


class RealReleaseAuditBoundary:
    def audit(self, *, audit_id: str, pre_real_verified: bool,
              shadow_passed: bool, safety_ready: bool,
              broker_boundary_ready: bool, explicit_real_contract: bool) -> RealReleaseAudit:
        if not audit_id.strip():
            raise ValueError("audit_id é obrigatório.")
        prerequisites = ("P111", "P112", "P113", "P114", "P115")
        reasons = []
        for ok, label in (
            (pre_real_verified, "P111 não verificado"),
            (explicit_real_contract, "contrato REAL não está explícito"),
            (broker_boundary_ready, "fronteira multi-corretora não está pronta"),
            (safety_ready, "segurança REAL não está pronta"),
            (shadow_passed, "shadow validation não passou"),
        ):
            if not ok:
                reasons.append(label)
        return RealReleaseAudit(audit_id, ReleaseAuditStatus.VERIFIED if not reasons else ReleaseAuditStatus.BLOCKED, prerequisites, tuple(reasons))
