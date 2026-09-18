from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import weakref


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
# thereby satisfy the REAL authorization issuer. Equality-based containers
# such as WeakSet are insufficient here because a separately fabricated,
# field-identical dataclass compares equal to the genuine object. The registry
# below therefore verifies object identity while retaining weak references.
# This is an in-process provenance guard; it is not a cryptographic identity
# system and does not claim to authenticate an external human/operator.
_VERIFIED_AUDITS: dict[int, weakref.ReferenceType[RealReleaseAudit]] = {}


def _is_boundary_verified_audit(audit: object) -> bool:
    if not isinstance(audit, RealReleaseAudit):
        return False
    reference = _VERIFIED_AUDITS.get(id(audit))
    return reference is not None and reference() is audit


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
            key = id(audit)
            _VERIFIED_AUDITS[key] = weakref.ref(
                audit,
                lambda _reference, key=key: _VERIFIED_AUDITS.pop(key, None),
            )
        return audit
