from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MaterialVerdict(str, Enum):
    KNOWN = "KNOWN"
    CONSISTENT = "CONSISTENT"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIED = "UNVERIFIED"


class EffectivenessVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    MIXED = "MIXED"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


@dataclass(frozen=True)
class KnowledgeReference:
    """A trusted proposition from the ecosystem's reviewed knowledge base."""

    reference_id: str
    statement: str
    topics: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaterialClaimReview:
    claim: str
    verdict: MaterialVerdict
    rationale: str
    matching_reference_ids: tuple[str, ...] = ()
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.claim.strip():
            raise ValueError("claim is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class MaterialEffectivenessReview:
    verdict: EffectivenessVerdict
    rationale: str
    sample_size: int | None = None
    tested_period: str | None = None

    def __post_init__(self) -> None:
        if self.sample_size is not None and self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")


@dataclass(frozen=True)
class LearningMaterialReview:
    resource_id: str
    knowledge_level: MaterialVerdict
    overall_verdict: MaterialVerdict
    claims: tuple[MaterialClaimReview, ...]
    effectiveness: MaterialEffectivenessReview
    limitations: tuple[str, ...] = ()
    operation_authorized: bool = False


class LearningMaterialReviewer:
    """Reviews supplied learning material without granting trading authority.

    A URL alone is never evidence. Claims must be compared with reviewed
    knowledge and/or explicit evidence. Conceptual consistency and strategy
    effectiveness are separate assessments.
    """

    def review(
        self,
        *,
        resource_id: str,
        claims: tuple[str, ...] | list[str],
        references: tuple[KnowledgeReference, ...] | list[KnowledgeReference] = (),
        contradicted_reference_ids: tuple[str, ...] | list[str] = (),
        contradicted_claims: dict[str, tuple[str, ...] | list[str]] | None = None,
        effectiveness: MaterialEffectivenessReview | None = None,
        material_content_verified: bool = False,
    ) -> LearningMaterialReview:
        if not resource_id.strip():
            raise ValueError("resource_id is required")
        if not material_content_verified:
            unknown_claims = tuple(
                MaterialClaimReview(
                    claim=claim.strip(),
                    verdict=MaterialVerdict.UNVERIFIED,
                    rationale="O conteúdo do material ainda não foi verificado; o link/vídeo, sozinho, não prova a afirmação.",
                )
                for claim in claims
                if claim.strip()
            )
            return LearningMaterialReview(
                resource_id=resource_id,
                knowledge_level=MaterialVerdict.UNVERIFIED,
                overall_verdict=MaterialVerdict.UNVERIFIED,
                claims=unknown_claims,
                effectiveness=effectiveness or MaterialEffectivenessReview(EffectivenessVerdict.NOT_ASSESSABLE, "Não há evidência verificada suficiente para avaliar eficácia."),
                limitations=("Conteúdo externo ainda não verificado.",),
            )

        ref_by_id = {item.reference_id: item for item in references if item.reference_id.strip()}
        ref_by_statement = {item.statement.strip().casefold(): item for item in references if item.statement.strip()}
        legacy_ids = {item.strip() for item in contradicted_reference_ids if item.strip()}
        explicit_contradictions = {
            str(claim).strip().casefold(): tuple(
                ref_id.strip() for ref_id in ref_ids if str(ref_id).strip() in ref_by_id
            )
            for claim, ref_ids in (contradicted_claims or {}).items()
        }

        reviewed: list[MaterialClaimReview] = []
        for claim in claims:
            normalized = claim.strip()
            if not normalized:
                continue
            contradiction_ids = explicit_contradictions.get(normalized.casefold(), ())
            if contradiction_ids:
                reviewed.append(MaterialClaimReview(
                    normalized,
                    MaterialVerdict.CONTRADICTED,
                    "A afirmação está explicitamente associada a referência(s) revisada(s) que a contradizem; exige revisão antes de ser tratada como conhecimento.",
                    contradiction_ids,
                    0.9,
                ))
                continue
            exact = ref_by_statement.get(normalized.casefold())
            if exact is not None:
                reviewed.append(MaterialClaimReview(
                    normalized,
                    MaterialVerdict.KNOWN,
                    "A afirmação coincide com conhecimento revisado do ecossistema.",
                    (exact.reference_id,),
                    1.0,
                ))
                continue
            # Legacy contradiction input is deliberately conservative: an ID by
            # itself cannot contradict an arbitrary claim. It is only accepted
            # when that reference is explicitly represented in the new mapping.
            _ = legacy_ids
            reviewed.append(MaterialClaimReview(
                normalized,
                MaterialVerdict.UNVERIFIED,
                "O material foi verificado, mas esta afirmação não possui evidência suficiente no conhecimento revisado fornecido.",
            ))

        verdicts = {item.verdict for item in reviewed}
        if MaterialVerdict.CONTRADICTED in verdicts:
            overall = MaterialVerdict.CONTRADICTED
        elif reviewed and verdicts == {MaterialVerdict.KNOWN}:
            overall = MaterialVerdict.KNOWN
        elif reviewed and MaterialVerdict.KNOWN in verdicts:
            overall = MaterialVerdict.CONSISTENT
        else:
            overall = MaterialVerdict.UNVERIFIED
        knowledge_level = MaterialVerdict.KNOWN if overall is MaterialVerdict.KNOWN else overall
        return LearningMaterialReview(
            resource_id=resource_id,
            knowledge_level=knowledge_level,
            overall_verdict=overall,
            claims=tuple(reviewed),
            effectiveness=effectiveness or MaterialEffectivenessReview(EffectivenessVerdict.NOT_ASSESSABLE, "A eficácia não pode ser concluída apenas pelo conteúdo do vídeo/link."),
            limitations=("Validade conceitual e eficácia operacional são avaliações separadas.",),
        )
