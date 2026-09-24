"""Senior-grade intelligence standard for the whole trading ecosystem.

This module does not pretend to make the system omniscient. It establishes the
minimum professional posture that every market interpretation must preserve:
whole-context observation, temporal reasoning, validated knowledge, evidence,
independence, counterevidence, uncertainty, provenance and reassessment.

The knowledge domains are intentionally descriptive rather than a closed
catalogue. New domains, relationships and discoveries can enter through the
existing validation pipeline without changing this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .p55_trusted_knowledge import TrustedKnowledge
from .whole_graph_observation import WholeGraphObservation, WholeGraphStatus


class SeniorIntelligenceStatus(str, Enum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class SeniorKnowledgeStandard:
    """Foundational professional knowledge posture, not a strategy catalogue."""

    principles: tuple[str, ...]
    domains: tuple[str, ...]
    open_ended: bool = True


@dataclass(frozen=True)
class SeniorIntelligenceAssessment:
    status: SeniorIntelligenceStatus
    context_id: str
    knowledge_ids: tuple[str, ...]
    principles_checked: tuple[str, ...]
    strengths: tuple[str, ...]
    gaps: tuple[str, ...]
    required_reassessment: tuple[str, ...]
    execution_authorized: bool = False


DEFAULT_SENIOR_KNOWLEDGE_STANDARD = SeniorKnowledgeStandard(
    principles=(
        "observar o mercado como um contexto e não como um sinal isolado",
        "integrar passado, presente e cenários futuros condicionais",
        "distinguir fato observado, interpretação, hipótese e conhecimento validado",
        "procurar evidência a favor e contra a leitura atual",
        "separar confluência independente de repetição do mesmo fenômeno",
        "considerar regime, estrutura, volatilidade, liquidez, fluxo/volume quando disponível e comportamento do preço",
        "considerar contexto macro, notícias e eventos quando forem materialmente relevantes e houver dados confiáveis",
        "considerar validação antes de promover descoberta, hipótese ou informação externa a conhecimento confiável",
        "tratar risco, execução, qualidade dos dados e segurança como partes da análise profissional",
        "reavaliar a leitura quando novas evidências contradizem ou mudam o contexto",
        "preservar incerteza quando a evidência não sustenta uma conclusão",
        "registrar proveniência para permitir auditoria e aprendizado",
    ),
    domains=(
        "estrutura e ação do preço",
        "tendência, regime e transições",
        "volatilidade e distribuição do movimento",
        "liquidez, volume e microestrutura quando disponíveis",
        "suporte, resistência, topos, fundos, rompimentos e pullbacks como fenômenos contextuais",
        "candles, corpo, pavios, rejeições, pressão e força como observações contextuais",
        "estatística, probabilidade e qualidade da evidência",
        "risco, execução e preservação de capital",
        "comportamento, vieses e tomada de decisão",
        "macro, notícias e eventos de mercado",
        "validação, memória, auditoria e aprendizado contínuo",
    ),
)


class SeniorMarketIntelligenceBoundary:
    """Checks that a market cycle meets the senior-grade reasoning posture."""

    def assess(
        self,
        *,
        graph: WholeGraphObservation,
        trusted_knowledge: Iterable[TrustedKnowledge] = (),
        standard: SeniorKnowledgeStandard = DEFAULT_SENIOR_KNOWLEDGE_STANDARD,
    ) -> SeniorIntelligenceAssessment:
        if not isinstance(graph, WholeGraphObservation):
            raise ValueError("whole graph observation is required")
        if not isinstance(standard, SeniorKnowledgeStandard):
            raise ValueError("invalid senior knowledge standard")

        knowledge = tuple(trusted_knowledge)
        if any(not isinstance(item, TrustedKnowledge) for item in knowledge):
            raise ValueError("trusted_knowledge must contain validated knowledge only")

        knowledge_ids = tuple(dict.fromkeys(item.knowledge_id for item in knowledge))
        gaps: list[str] = []
        strengths: list[str] = []
        reassessment: list[str] = []

        if graph.status is WholeGraphStatus.INSUFFICIENT:
            status = SeniorIntelligenceStatus.INSUFFICIENT
            gaps.append("não existe contexto disponível suficiente para uma leitura sênior")
        elif graph.status is WholeGraphStatus.PARTIAL:
            status = SeniorIntelligenceStatus.PARTIAL
            gaps.extend(f"contexto não observado: {gap.node_id} — {gap.reason}" for gap in graph.gaps)
            reassessment.append("reavaliar quando os dados ausentes estiverem disponíveis")
        else:
            status = SeniorIntelligenceStatus.READY
            strengths.append("todo o contexto materialmente disponibilizado foi contabilizado")

        if knowledge_ids:
            strengths.append("conhecimento externo usado possui proveniência de validação")
        else:
            strengths.append(
                "o ciclo já dispõe do conhecimento profissional basal incorporado no padrão sênior; "
                "ausência de conhecimento externo adicional não reduz essa capacidade"
            )

        strengths.append("o padrão sênior exige evidência favorável e contrária, não votação de sinais")
        strengths.append("novas descobertas permanecem sujeitas à validação antes de promoção")
        reassessment.append("reavaliar se nova evidência alterar o contexto, a relação observada ou a hipótese")

        return SeniorIntelligenceAssessment(
            status=status,
            context_id=graph.context_id,
            knowledge_ids=knowledge_ids,
            principles_checked=standard.principles,
            strengths=tuple(dict.fromkeys(strengths)),
            gaps=tuple(dict.fromkeys(gaps)),
            required_reassessment=tuple(dict.fromkeys(reassessment)),
            execution_authorized=False,
        )
