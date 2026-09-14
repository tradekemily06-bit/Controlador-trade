"""Auditable provenance matrix for the senior professional knowledge layer."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .financial_market_curriculum import SeniorFinancialMarketCurriculum
from .senior_professional_depth import build_senior_professional_depth


class KnowledgeStatus(str, Enum):
    UNVALIDATED = "UNVALIDATED"
    VALIDATED = "VALIDATED"
    REASSESS = "REASSESS"


@dataclass(frozen=True)
class KnowledgeEvidence:
    source_id: str
    source_title: str
    source_version: str
    published_or_updated_at: str
    validated_at: str
    validator: str
    test_id: str
    evidence_note: str

    def validate(self) -> None:
        values = (
            self.source_id,
            self.source_title,
            self.source_version,
            self.published_or_updated_at,
            self.validated_at,
            self.validator,
            self.test_id,
            self.evidence_note,
        )
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("knowledge evidence requires complete provenance fields")


@dataclass(frozen=True)
class KnowledgeCompetency:
    competency_id: str
    module_id: str
    domain: str
    competency: str
    experience_years: int = 45
    experience_is_open_ended: bool = True
    status: KnowledgeStatus = KnowledgeStatus.UNVALIDATED
    evidence: tuple[KnowledgeEvidence, ...] = ()
    last_reviewed_at: str | None = None
    next_review_reason: str | None = None
    execution_authorized: bool = False

    def validate(self) -> None:
        if not self.competency_id.strip() or not self.module_id.strip():
            raise ValueError("knowledge competency identity is required")
        if not self.domain.strip() or not self.competency.strip():
            raise ValueError("knowledge competency domain and description are required")
        if self.experience_years < 45:
            raise ValueError("knowledge competency must preserve the 45+ experience baseline")
        if not self.experience_is_open_ended:
            raise ValueError("knowledge experience cannot have an upper ceiling")
        if self.execution_authorized:
            raise ValueError("knowledge validation cannot authorize execution")
        if self.status is KnowledgeStatus.VALIDATED:
            if not self.evidence:
                raise ValueError("validated knowledge requires evidence")
            if not self.last_reviewed_at:
                raise ValueError("validated knowledge requires review timestamp")
            for evidence in self.evidence:
                evidence.validate()


class SeniorProfessionalKnowledgeMatrix:
    """Trace curriculum and advanced professional depth to evidence."""

    def __init__(self, curriculum: SeniorFinancialMarketCurriculum | None = None) -> None:
        self.curriculum = curriculum or SeniorFinancialMarketCurriculum()
        self._records: dict[str, KnowledgeCompetency] = {}
        self._build_from_curriculum()
        self._build_from_advanced_depth()

    @property
    def records(self) -> tuple[KnowledgeCompetency, ...]:
        return tuple(self._records.values())

    def by_module(self, module_id: str) -> tuple[KnowledgeCompetency, ...]:
        return tuple(record for record in self.records if record.module_id == module_id)

    def get(self, competency_id: str) -> KnowledgeCompetency:
        return self._records[competency_id]

    def register_evidence(
        self,
        competency_id: str,
        *,
        evidence: KnowledgeEvidence,
        reviewed_at: str,
        next_review_reason: str | None = None,
    ) -> KnowledgeCompetency:
        evidence.validate()
        current = self.get(competency_id)
        updated = KnowledgeCompetency(
            competency_id=current.competency_id,
            module_id=current.module_id,
            domain=current.domain,
            competency=current.competency,
            experience_years=current.experience_years,
            experience_is_open_ended=True,
            status=KnowledgeStatus.VALIDATED,
            evidence=(*current.evidence, evidence),
            last_reviewed_at=reviewed_at,
            next_review_reason=next_review_reason,
            execution_authorized=False,
        )
        updated.validate()
        self._records[competency_id] = updated
        return updated

    def mark_for_reassessment(self, competency_id: str, reason: str) -> KnowledgeCompetency:
        current = self.get(competency_id)
        if not reason.strip():
            raise ValueError("reassessment reason is required")
        updated = KnowledgeCompetency(
            competency_id=current.competency_id,
            module_id=current.module_id,
            domain=current.domain,
            competency=current.competency,
            experience_years=current.experience_years,
            experience_is_open_ended=True,
            status=KnowledgeStatus.REASSESS,
            evidence=current.evidence,
            last_reviewed_at=current.last_reviewed_at,
            next_review_reason=reason,
            execution_authorized=False,
        )
        updated.validate()
        self._records[competency_id] = updated
        return updated

    def status_counts(self) -> dict[KnowledgeStatus, int]:
        counts = {status: 0 for status in KnowledgeStatus}
        for record in self.records:
            counts[record.status] += 1
        return counts

    def _add(self, record: KnowledgeCompetency) -> None:
        record.validate()
        self._records[record.competency_id] = record

    def _build_from_curriculum(self) -> None:
        for module in self.curriculum.modules:
            competencies = (*module.practical_competencies, *module.senior_capabilities)
            for index, competency in enumerate(_unique(competencies), start=1):
                self._add(KnowledgeCompetency(
                    competency_id=f"{module.module_id}-C{index:02d}",
                    module_id=module.module_id,
                    domain=module.domain.value,
                    competency=competency,
                ))

    def _build_from_advanced_depth(self) -> None:
        for depth in build_senior_professional_depth():
            for index, competency in enumerate(depth.competencies, start=1):
                self._add(KnowledgeCompetency(
                    competency_id=f"DEPTH-{depth.domain_id.upper()}-C{index:02d}",
                    module_id=f"DEPTH-{depth.domain_id.upper()}",
                    domain=depth.domain_id,
                    competency=competency,
                    experience_years=depth.experience_years,
                    experience_is_open_ended=depth.experience_is_open_ended,
                ))


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))
