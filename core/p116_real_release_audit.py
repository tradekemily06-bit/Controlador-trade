from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from weakref import WeakSet


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


# A verified audit must come from the release-audit boundary itself. A caller
# must not be able to manufacture a VERIFIED dataclass with the same fields and
# thereby satisfy the REAL authorization issuer. This is an in-process
# provenance guard; it is not a cryptographic identity system and does not
# claim to authenticate an external human/operator.
_VERIFIED_AUDITS: WeakSet[RealReleaseAudit] = WeakSet()


def _is_boundary_verified_audit(audit: object) -> bool:
    return isinstance(audit, RealReleaseAudit) and audit in _VERIFIED_AUDITS


class RealReleaseAuditBoundary:
    def audit(self, *, audit_id: str, pre_real_verified: bool,
              shadow_passed: bool, safety_ready: bool,
              broker_boundary_ready: bool, explicit_real_contract: bool) -> RealReleaseAudit:
        if not isinstance(audit_id, str) or not audit_id.strip():
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
            if ok is not True:
                reasons.append(label)
        audit = RealReleaseAudit(
            audit_id,
            ReleaseAuditStatus.VERIFIED if not reasons else ReleaseAuditStatus.BLOCKED,
            prerequisites,
            tuple(reasons),
        )
        if audit.verified:
            _VERIFIED_AUDITS.add(audit)
        return audit
