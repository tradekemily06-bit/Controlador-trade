from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from data.models import Candle

from .integrated_market_reading import IntegratedMarketReading, ReadingStatus
from .temporal_market_context import TemporalMarketContext


class ReasoningPosture(str, Enum):
    ACT = "ACT"
    WAIT = "WAIT"
    REASSESS = "REASSESS"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class ProfessionalQuestion:
    category: str
    question: str


@dataclass(frozen=True)
class SeniorMarketAssessment:
    """Contextual professional reasoning, not an order engine.

    The assessment explicitly separates what the market shows, what remains
    uncertain, what deserves observation, and what should not be assumed.
    It never grants execution authority and never turns question count into
    a score or vote.
    """

    posture: ReasoningPosture
    context_statement: str
    observations: tuple[str, ...]
    considerations: tuple[str, ...]
    avoid_assumptions: tuple[str, ...]
    questions: tuple[ProfessionalQuestion, ...]
    evidence_for: tuple[str, ...]
    evidence_against: tuple[str, ...]
    uncertainty: tuple[str, ...]
    execution_authorized: bool = False


class SeniorMarketReasoner:
    """Reason like an experienced market professional without rigid rules.

    This layer asks the questions a senior analyst would ask before acting,
    compares historical context with the present, checks contradictions, and
    states what should be observed or avoided. It is deliberately downstream
    of factual/contextual observations and upstream of any operational gate.
    """

    def assess(
        self,
        candles: list[Candle],
        reading: IntegratedMarketReading,
        temporal: TemporalMarketContext,
    ) -> SeniorMarketAssessment:
        if not candles or reading.status is ReadingStatus.INSUFFICIENT:
            return SeniorMarketAssessment(
                posture=ReasoningPosture.INSUFFICIENT,
                context_statement="Ainda não há evidência contextual suficiente para uma leitura profissional completa.",
                observations=(),
                considerations=("Preservar a incerteza e buscar mais contexto antes de concluir." ,),
                avoid_assumptions=("Não transformar ausência de evidência em uma direção de mercado." ,),
                questions=(
                    ProfessionalQuestion("histórico", "O histórico disponível é suficiente para entender de onde o movimento veio?"),
                    ProfessionalQuestion("evidência", "O que ainda falta observar antes de uma conclusão responsável?"),
                ),
                evidence_for=(),
                evidence_against=(),
                uncertainty=("Contexto insuficiente.",),
            )

        observations: list[str] = []
        considerations: list[str] = []
        avoid: list[str] = []
        questions: list[ProfessionalQuestion] = []

        if temporal.historical:
            observations.append("O histórico foi separado da leitura do presente para evitar interpretar o último candle isoladamente.")
        if temporal.present:
            observations.extend(obs.statement for obs in temporal.present)

        if temporal.scenarios:
            considerations.extend(
                f"Cenário condicional: {scenario.condition} → {scenario.implication}."
                for scenario in temporal.scenarios
            )

        if reading.status is ReadingStatus.CONFLICTING:
            posture = ReasoningPosture.REASSESS
            avoid.append("Não escolher o lado vencedor pela quantidade de sinais.")
            avoid.append("Não tratar uma confluência aparente como independente sem verificar se descreve o mesmo fenômeno.")
            questions.append(ProfessionalQuestion("conflito", "Qual evidência explica melhor a divergência e qual evidência pode estar sendo supervalorizada?"))
            questions.append(ProfessionalQuestion("reavaliação", "O que precisaria acontecer para uma das hipóteses perder força?"))
        elif reading.possible_false_breakout:
            posture = ReasoningPosture.REASSESS
            avoid.append("Não assumir que uma excursão além do range seja, por si só, um rompimento confirmado.")
            questions.append(ProfessionalQuestion("estrutura", "O comportamento posterior confirma o deslocamento ou exige reavaliação?"))
        else:
            posture = ReasoningPosture.WAIT
            considerations.append("A leitura atual deve permanecer condicional até que o contexto e as evidências sejam coerentes.")

        questions.extend(
            (
                ProfessionalQuestion("contexto", "O que aconteceu antes e como isso altera o significado do movimento atual?"),
                ProfessionalQuestion("presente", "O que mudou agora em relação ao contexto anterior?"),
                ProfessionalQuestion("causa", "Quais relações observáveis podem explicar o comportamento sem assumir causalidade sem evidência?"),
                ProfessionalQuestion("contraprova", "O que contradiz a interpretação atual?"),
                ProfessionalQuestion("decisão", "O que um profissional experiente faria agora e, igualmente importante, o que ele evitaria fazer?"),
                ProfessionalQuestion("reversão", "O que faria esta leitura precisar ser abandonada ou reformulada?"),
            )
        )

        evidence_for = tuple(reading.supporting)
        evidence_against = tuple(reading.contradicting)
        uncertainty = tuple(reading.conflicts) + tuple(
            "O futuro permanece condicional; nenhum cenário é tratado como previsão garantida."
            for _ in (1,)
        )

        context_statement = (
            "Leitura integrada entre histórico, presente e cenários condicionais; "
            "a experiência é representada por perguntas, comparação de evidências e reavaliação, "
            "não por uma lista fixa de regras."
        )

        return SeniorMarketAssessment(
            posture=posture,
            context_statement=context_statement,
            observations=tuple(observations),
            considerations=tuple(dict.fromkeys(considerations)),
            avoid_assumptions=tuple(dict.fromkeys(avoid)),
            questions=tuple(questions),
            evidence_for=evidence_for,
            evidence_against=evidence_against,
            uncertainty=uncertainty,
            execution_authorized=False,
        )
