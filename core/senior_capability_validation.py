"""Admission boundary for capabilities that are allowed to influence trusted operation.

A capability can exist as a design/profile/research concept without being trusted.
Operationally relevant capability must have a traceable positive test/validation
and a memory record. This keeps the senior-experience layer from becoming an
unsupported claim while preserving open-ended future domains.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p83_validation_decision import ValidationDecision, ValidationDecisionStatus
from core.p57_knowledge_memory import KnowledgeMemoryRecord


class CapabilityTrust(str, Enum):
    VALIDATED = "VALIDATED"
    UNVALIDATED = "UNVALIDATED"
    INCONSISTENT = "INCONSISTENT"


@dataclass(frozen=True)
class SeniorCapabilityEvidence:
    capability_id: str
    domain: str
    validation_decision_id: str | None = None
    memory_id: str | None = None


@dataclass(frozen=True)
class SeniorCapabilityAdmission:
    capability_id: str
    domain: str
    trust: CapabilityTrust
    validation_decision_id: str | None
    memory_id: str | None
    rationale: str


def admit_senior_capability(
    evidence: SeniorCapabilityEvidence,
    *,
    validation: ValidationDecision | None,
    memory: KnowledgeMemoryRecord | None,
) -> SeniorCapabilityAdmission:
    """Admit a capability only when test/validation and memory agree.

    This boundary never grants execution authority. It only determines whether
    a capability may be treated as trusted evidence by downstream analysis.
    """
    if not isinstance(evidence, SeniorCapabilityEvidence):
        raise ValueError("invalid senior capability evidence")
    if not evidence.capability_id.strip():
        raise ValueError("capability_id is required")
    if not evidence.domain.strip():
        raise ValueError("domain is required")

    if validation is None or memory is None:
        return SeniorCapabilityAdmission(
            evidence.capability_id.strip(), evidence.domain.strip(),
            CapabilityTrust.UNVALIDATED,
            evidence.validation_decision_id, evidence.memory_id,
            "Capability exists, but validation/test and memory evidence are incomplete.",
        )

    if validation.status is not ValidationDecisionStatus.VALIDATED:
        return SeniorCapabilityAdmission(
            evidence.capability_id.strip(), evidence.domain.strip(),
            CapabilityTrust.UNVALIDATED,
            validation.decision_id, memory.memory_id,
            "Capability is not backed by a validated positive result.",
        )

    if validation.test_id != memory.test_id or validation.hypothesis_id != memory.hypothesis_id:
        return SeniorCapabilityAdmission(
            evidence.capability_id.strip(), evidence.domain.strip(),
            CapabilityTrust.INCONSISTENT,
            validation.decision_id, memory.memory_id,
            "Validation and memory provenance do not match.",
        )

    return SeniorCapabilityAdmission(
        evidence.capability_id.strip(), evidence.domain.strip(),
        CapabilityTrust.VALIDATED,
        validation.decision_id, memory.memory_id,
        "Capability has matching positive validation and retained memory provenance.",
    )
