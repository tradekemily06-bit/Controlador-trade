from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ReadinessState(str, Enum):
    NOT_READY = "NOT_READY"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"


@dataclass(frozen=True)
class ReadinessEvidenceRef:
    """Traceable proof reference bound to the exact audit target commit.

    This record identifies where proof lives. It does not fetch or authenticate
    external evidence; the caller must provide the actual current evidence.
    """

    gate: str
    evidence_id: str
    source_ref: str
    commit_sha: str

    def __post_init__(self) -> None:
        for name in ("gate", "evidence_id", "source_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if not isinstance(self.commit_sha, str) or not _SHA_RE.fullmatch(self.commit_sha.strip().lower()):
            raise ValueError("commit_sha must be a 40-character hexadecimal SHA")


@dataclass(frozen=True)
class FinalReadinessEvidence:
    target_commit_sha: str
    stage2_green: bool
    stage3_green: bool
    stage4_green: bool
    stage5_green: bool
    stage6_green: bool
    side_doors_scanned: bool
    threat_model_reviewed: bool
    secrets_reviewed: bool
    rollback_tested: bool
    reconciliation_tested: bool
    incident_response_tested: bool
    demo_real_separation_tested: bool
    legacy_compatibility_tested: bool
    ci_green: bool
    evidence_refs: tuple[ReadinessEvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.target_commit_sha, str) or not _SHA_RE.fullmatch(self.target_commit_sha.strip().lower()):
            raise ValueError("target_commit_sha must be a 40-character hexadecimal SHA")


@dataclass(frozen=True)
class FinalReadinessAssessment:
    state: ReadinessState
    missing: tuple[str, ...]
    real_enabled: bool = False


_REQUIRED = (
    "stage2_green",
    "stage3_green",
    "stage4_green",
    "stage5_green",
    "stage6_green",
    "side_doors_scanned",
    "threat_model_reviewed",
    "secrets_reviewed",
    "rollback_tested",
    "reconciliation_tested",
    "incident_response_tested",
    "demo_real_separation_tested",
    "legacy_compatibility_tested",
    "ci_green",
)


def assess_final_readiness(evidence: FinalReadinessEvidence) -> FinalReadinessAssessment:
    if not isinstance(evidence, FinalReadinessEvidence):
        raise TypeError("final readiness evidence is required")

    missing = [name for name in _REQUIRED if getattr(evidence, name) is not True]
    invalid_refs = [ref for ref in evidence.evidence_refs if not isinstance(ref, ReadinessEvidenceRef)]
    if invalid_refs:
        missing.append("invalid_evidence_ref")

    valid_refs = [ref for ref in evidence.evidence_refs if isinstance(ref, ReadinessEvidenceRef)]
    invalid_gates = [ref.gate for ref in valid_refs if ref.gate not in _REQUIRED]
    if invalid_gates:
        missing.append("invalid_evidence_gate")

    duplicate_gates = {
        gate
        for gate in (ref.gate for ref in valid_refs)
        if sum(item.gate == gate for item in valid_refs) > 1
    }
    if duplicate_gates:
        missing.append("duplicate_evidence_gate")

    stale_refs = [
        ref.gate for ref in valid_refs
        if ref.commit_sha.strip().lower() != evidence.target_commit_sha.strip().lower()
    ]
    if stale_refs:
        missing.append("stale_evidence_commit")

    refs_by_gate = {ref.gate: ref for ref in valid_refs if ref.gate in _REQUIRED}
    missing.extend(
        f"{name}_evidence"
        for name in _REQUIRED
        if getattr(evidence, name) is True and name not in refs_by_gate
    )

    if missing:
        return FinalReadinessAssessment(ReadinessState.NOT_READY, tuple(dict.fromkeys(missing)), real_enabled=False)

    return FinalReadinessAssessment(ReadinessState.READY_FOR_REVIEW, (), real_enabled=False)
