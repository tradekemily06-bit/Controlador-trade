"""Senior, evidence-driven prioritization of assets for analysis.

This layer answers a different question from execution: "which currently
available assets deserve attention now?" It never authorizes a trade.

The broker universe remains complete. Suitability is contextual and can be
INSUFFICIENT when evidence is missing. No asset class is intrinsically
preferred; current market/data/execution evidence must justify priority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class AssetSuitability(str, Enum):
    PRIORITY = "PRIORITY"
    WATCH = "WATCH"
    INSUFFICIENT = "INSUFFICIENT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AssetSuitabilityObservation:
    symbol: str
    asset_class: str
    tradeable: bool
    quote_available: bool
    session_open: bool | None
    weekend_capable: bool
    quote_fresh: bool | None = None
    quote_timestamped: bool | None = None
    spread_observed: float | None = None
    liquidity_observed: bool | None = None
    data_quality_ok: bool | None = None
    domain_expertise_available: bool = False
    unresolved_questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeniorAssetAssessment:
    symbol: str
    asset_class: str
    suitability: AssetSuitability
    evidence: tuple[str, ...]
    gaps: tuple[str, ...]
    rationale: str

    @property
    def attention_priority(self) -> bool:
        return self.suitability is AssetSuitability.PRIORITY


def assess_asset(observation: AssetSuitabilityObservation) -> SeniorAssetAssessment:
    """Assess whether an asset deserves analysis attention from current evidence."""
    evidence: list[str] = []
    gaps = list(observation.unresolved_questions)

    if not observation.tradeable:
        return SeniorAssetAssessment(
            observation.symbol, observation.asset_class,
            AssetSuitability.UNAVAILABLE, (), tuple(gaps),
            "Ativo não está atualmente negociável pelo estado observado.",
        )
    if not observation.quote_available:
        return SeniorAssetAssessment(
            observation.symbol, observation.asset_class,
            AssetSuitability.UNAVAILABLE, (), tuple(gaps),
            "Cotação atual indisponível; não é possível avaliar adequadamente.",
        )
    if observation.session_open is False:
        return SeniorAssetAssessment(
            observation.symbol, observation.asset_class,
            AssetSuitability.UNAVAILABLE, ("sessão fechada",), tuple(gaps),
            "A sessão atual está fechada.",
        )
    if observation.session_open is None:
        gaps.append("estado da sessão não confirmado")
    else:
        evidence.append("sessão aberta confirmada")

    if observation.data_quality_ok is False:
        gaps.append("qualidade de dados inadequada")
    elif observation.data_quality_ok is True:
        evidence.append("qualidade de dados observada como adequada")
    else:
        gaps.append("qualidade de dados não confirmada")

    if observation.quote_fresh is False:
        gaps.append("cotação não está fresca")
    elif observation.quote_fresh is True:
        evidence.append("frescura da cotação confirmada")
    elif observation.quote_timestamped is True:
        gaps.append("frescura da cotação ainda não foi calculada")
        evidence.append("cotação com marca temporal observada")
    else:
        gaps.append("frescura da cotação não confirmada")

    if observation.liquidity_observed is True:
        evidence.append("liquidez observada")
    elif observation.liquidity_observed is False:
        gaps.append("liquidez não demonstrada")
    else:
        gaps.append("liquidez não confirmada")

    if not observation.domain_expertise_available:
        gaps.append("expertise do domínio ainda requer validação/teste/memória")
    else:
        evidence.append("expertise de domínio validada")

    if observation.spread_observed is not None:
        evidence.append("spread observado")
    else:
        gaps.append("spread não observado")

    material_gaps = len(gaps)
    if material_gaps == 0 and len(evidence) >= 4:
        suitability = AssetSuitability.PRIORITY
        rationale = "Evidência atual suficiente para priorizar o ativo para análise."
    elif evidence and material_gaps < 4:
        suitability = AssetSuitability.WATCH
        rationale = "Ativo é analisável, mas ainda possui lacunas materiais que exigem acompanhamento."
    else:
        suitability = AssetSuitability.INSUFFICIENT
        rationale = "Há evidência insuficiente para afirmar que este é um bom ativo para trabalhar agora."

    return SeniorAssetAssessment(
        observation.symbol, observation.asset_class, suitability,
        tuple(evidence), tuple(gaps), rationale,
    )


def prioritize_assets(
    observations: Iterable[AssetSuitabilityObservation],
) -> tuple[SeniorAssetAssessment, ...]:
    """Return all observed assets ordered by current suitability, never by class."""
    assessments = tuple(assess_asset(item) for item in observations)
    order = {
        AssetSuitability.PRIORITY: 0,
        AssetSuitability.WATCH: 1,
        AssetSuitability.INSUFFICIENT: 2,
        AssetSuitability.UNAVAILABLE: 3,
    }
    return tuple(sorted(assessments, key=lambda item: (order[item.suitability], item.symbol)))
