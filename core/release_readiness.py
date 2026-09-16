from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReadinessState(str, Enum):
    NOT_READY = "NOT_READY"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"


@dataclass(frozen=True)
class FinalReadinessEvidence:
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
    ci_green: bool


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
    "ci_green",
)


def assess_final_readiness(evidence: FinalReadinessEvidence) -> FinalReadinessAssessment:
    if not isinstance(evidence, FinalReadinessEvidence):
        raise TypeError("final readiness evidence is required")
    missing = tuple(name for name in _REQUIRED if getattr(evidence, name) is not True)
    if missing:
        return FinalReadinessAssessment(ReadinessState.NOT_READY, missing, real_enabled=False)
    # Stage 7 is governance only. Passing the matrix never creates REAL authority.
    return FinalReadinessAssessment(ReadinessState.READY_FOR_REVIEW, (), real_enabled=False)
