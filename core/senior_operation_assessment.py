"""Senior-grade assessment of whether an opportunity is actually suitable.

This module answers a narrower question than execution: does the currently
observed opportunity survive a professional quality review?  It never grants
execution authority.  A suitable opportunity still has to pass every
operational, risk, freshness, market-identity and execution gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .integrated_market_reading import IntegratedMarketReading, ReadingStatus
from .senior_market_intelligence import SeniorIntelligenceAssessment, SeniorIntelligenceStatus
from .senior_market_reasoning import ReasoningPosture, SeniorMarketAssessment
from .whole_graph_observation import WholeGraphObservation, WholeGraphStatus


class SeniorOperationDisposition(str, Enum):
    SUITABLE = "SUITABLE"
    WAIT = "WAIT"
    REASSESS = "REASSESS"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class SeniorOperationAssessment:
    """Professional opportunity-quality review, never an execution approval."""

    disposition: SeniorOperationDisposition
    quality_level: str
    reasons: tuple[str, ...]
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    invalidators: tuple[str, ...]
    evidence_for: tuple[str, ...]
    evidence_against: tuple[str, ...]
    independent_confluences: int
    execution_authorized: bool = False


class SeniorOperationAssessor:
    """Apply a conservative professional review to one contextual cycle."""

    def assess(
        self,
        *,
        graph: WholeGraphObservation,
        reading: IntegratedMarketReading,
        reasoning: SeniorMarketAssessment,
        intelligence: SeniorIntelligenceAssessment | None = None,
    ) -> SeniorOperationAssessment:
        if not isinstance(graph, WholeGraphObservation):
            raise ValueError("whole graph observation is required")
        if not isinstance(reading, IntegratedMarketReading):
            raise ValueError("integrated market reading is required")
        if not isinstance(reasoning, SeniorMarketAssessment):
            raise ValueError("senior market assessment is required")
        if intelligence is not None and not isinstance(intelligence, SeniorIntelligenceAssessment):
            raise ValueError("invalid senior intelligence assessment")

        reasons: list[str] = []
        strengths: list[str] = []
        weaknesses: list[str] = []
        invalidators: list[str] = []
        independent = reading.independent_confluences

        if graph.status is WholeGraphStatus.INSUFFICIENT:
            return self._result(
                SeniorOperationDisposition.INSUFFICIENT,
                "INSUFICIENTE",
                reasons=("O contexto disponível não é suficiente para avaliar a oportunidade como um profissional experiente." ,),
                weaknesses=("Há informação estrutural ausente.",),
                invalidators=("Completar o contexto material antes de considerar a oportunidade novamente.",),
                reading=reading,
            )

        if graph.status is WholeGraphStatus.PARTIAL:
            weaknesses.append("O contexto observado ainda é parcial.")
            invalidators.append("Reavaliar quando as lacunas materiais forem preenchidas.")

        if reading.status is ReadingStatus.INSUFFICIENT:
            weaknesses.append("A leitura integrada não tem evidência suficiente.")
        elif reading.status is ReadingStatus.CONFLICTING:
            weaknesses.append("Existem evidências direcionais conflitantes.")
            invalidators.append("Resolver a contradição antes de considerar entrada.")
        elif reading.status is ReadingStatus.SUPPORTED:
            strengths.append("A leitura integrada apresenta suporte direcional observável.")

        if reading.possible_false_breakout:
            weaknesses.append("Existe hipótese de falso rompimento sem confirmação suficiente.")
            invalidators.append("Não considerar a oportunidade enquanto a sustentação do rompimento não estiver clara.")

        if independent < 2:
            weaknesses.append("Há pouca confluência independente para uma leitura de grau sênior.")
            invalidators.append("Buscar confirmação independente real, sem contar duas vezes o mesmo fenômeno.")
        else:
            strengths.append(f"Há {independent} domínio(s) de evidência independente(s) contabilizado(s).")

        if reading.supporting:
            strengths.append("Existe evidência favorável explicitamente identificada.")
        if reading.contradicting:
            weaknesses.append("Existe evidência contrária explicitamente identificada.")

        if reasoning.posture is ReasoningPosture.REASSESS:
            weaknesses.append("A leitura profissional pede reavaliação antes de agir.")
        elif reasoning.posture is ReasoningPosture.INSUFFICIENT:
            weaknesses.append("A postura profissional é de contexto insuficiente.")
        elif reasoning.posture is ReasoningPosture.ACT:
            strengths.append("A postura profissional considera o contexto suficientemente coerente para uma oportunidade.")

        if intelligence is not None:
            if intelligence.status is SeniorIntelligenceStatus.INSUFFICIENT:
                weaknesses.append("A camada de inteligência sênior considera o contexto insuficiente.")
            elif intelligence.status is SeniorIntelligenceStatus.PARTIAL:
                weaknesses.append("A camada de inteligência sênior identifica lacunas de contexto.")
            else:
                strengths.append("A camada de inteligência sênior concluiu a revisão do contexto disponível.")

        hard_reassessment = (
            graph.status is not WholeGraphStatus.COMPLETE
            or reading.status is not ReadingStatus.SUPPORTED
            or reading.possible_false_breakout
            or reasoning.posture is not ReasoningPosture.ACT
        )
        suitable = (
            not hard_reassessment
            and independent >= 2
            and bool(reading.supporting)
            and not reading.contradicting
        )

        if suitable:
            disposition = SeniorOperationDisposition.SUITABLE
            quality = "SÊNIOR"
            reasons.append("A oportunidade sobreviveu à revisão contextual, de evidência, independência e contraprova.")
        elif hard_reassessment:
            disposition = SeniorOperationDisposition.REASSESS
            quality = "REAVALIAR"
            reasons.append("A oportunidade ainda contém contexto, evidência ou postura profissional que exige reavaliação.")
        else:
            disposition = SeniorOperationDisposition.WAIT
            quality = "AGUARDAR"
            reasons.append("A oportunidade não atingiu o padrão conservador de qualidade para uma leitura sênior.")

        return self._result(
            disposition,
            quality,
            reasons=tuple(dict.fromkeys(reasons)),
            strengths=tuple(dict.fromkeys(strengths)),
            weaknesses=tuple(dict.fromkeys(weaknesses)),
            invalidators=tuple(dict.fromkeys(invalidators)),
            reading=reading,
        )

    @staticmethod
    def _result(
        disposition: SeniorOperationDisposition,
        quality_level: str,
        *,
        reasons: tuple[str, ...],
        reading: IntegratedMarketReading,
        strengths: tuple[str, ...] = (),
        weaknesses: tuple[str, ...] = (),
        invalidators: tuple[str, ...] = (),
    ) -> SeniorOperationAssessment:
        return SeniorOperationAssessment(
            disposition=disposition,
            quality_level=quality_level,
            reasons=reasons,
            strengths=strengths,
            weaknesses=weaknesses,
            invalidators=invalidators,
            evidence_for=reading.supporting,
            evidence_against=reading.contradicting,
            independent_confluences=reading.independent_confluences,
            execution_authorized=False,
        )
