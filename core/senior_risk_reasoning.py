"""Senior risk reasoning for decision and autonomous-operation contexts.

This module represents risk as a first-class market-analysis domain. It does
not prescribe universal percentages or replace the operational RiskManager;
it organizes the risk questions an experienced professional should consider
before any action, whether execution is manual or autonomous.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class RiskKnowledgeStatus(str, Enum):
    ASSESSED = "ASSESSED"
    INSUFFICIENT = "INSUFFICIENT"
    REASSESS = "REASSESS"


class RiskDomain(str, Enum):
    CAPITAL = "CAPITAL"
    POSITION = "POSITION"
    DRAWDOWN = "DRAWDOWN"
    LEVERAGE_MARGIN = "LEVERAGE_MARGIN"
    CONCENTRATION = "CONCENTRATION"
    CORRELATION = "CORRELATION"
    LIQUIDITY = "LIQUIDITY"
    SLIPPAGE = "SLIPPAGE"
    COSTS = "COSTS"
    VOLATILITY = "VOLATILITY"
    GAP_EVENT = "GAP_EVENT"
    MARKET_REGIME = "MARKET_REGIME"
    MODEL_UNCERTAINTY = "MODEL_UNCERTAINTY"
    DATA_QUALITY = "DATA_QUALITY"
    EXECUTION = "EXECUTION"
    COUNTERPARTY = "COUNTERPARTY"
    OPERATIONAL = "OPERATIONAL"
    SECURITY = "SECURITY"
    RECOVERY = "RECOVERY"


@dataclass(frozen=True)
class RiskObservation:
    domain: RiskDomain
    statement: str
    known: bool
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeniorRiskAssessment:
    status: RiskKnowledgeStatus
    observations: tuple[RiskObservation, ...]
    material_risks: tuple[str, ...]
    unknowns: tuple[str, ...]
    questions: tuple[str, ...]
    reassessment_triggers: tuple[str, ...]
    execution_authorized: bool = False


class SeniorRiskReasoner:
    """Assess risk comprehensively without inventing missing facts.

    The same risk reasoning applies in manual and autonomous modes. Autonomous
    operation is intentionally not inferred from a good risk assessment; a
    separate authorization gate must decide whether the system may act alone.
    """

    _DOMAINS = tuple(RiskDomain)

    def assess(
        self,
        observations: Iterable[RiskObservation] = (),
        *,
        available_domains: Iterable[RiskDomain] = _DOMAINS,
    ) -> SeniorRiskAssessment:
        normalized = self._normalize_observations(observations)
        available = self._normalize_domains(available_domains)

        if not normalized:
            return SeniorRiskAssessment(
                status=RiskKnowledgeStatus.INSUFFICIENT,
                observations=(),
                material_risks=(),
                unknowns=tuple(domain.value for domain in available),
                questions=self._questions(available),
                reassessment_triggers=(
                    "Nova informação material de risco.",
                    "Mudança de regime, liquidez, volatilidade, exposição ou condições de execução.",
                    "Qualquer divergência entre estado esperado e estado efetivamente observado.",
                ),
                execution_authorized=False,
            )

        known_domains = {item.domain for item in normalized if item.known}
        unknown_domains = tuple(domain.value for domain in available if domain not in known_domains)
        material = tuple(
            item.statement.strip()
            for item in normalized
            if item.known and item.statement.strip()
        )
        status = RiskKnowledgeStatus.ASSESSED
        if unknown_domains:
            status = RiskKnowledgeStatus.REASSESS

        questions = self._questions(tuple(domain for domain in available if domain not in known_domains))
        if not questions:
            questions = (
                "As premissas de risco continuam válidas depois da mudança mais recente do mercado?",
                "Qual evidência contradiz a avaliação atual de risco?",
                "O risco observado é aceitável apenas no cenário atual ou permanece robusto em cenários adversos?",
            )

        return SeniorRiskAssessment(
            status=status,
            observations=normalized,
            material_risks=material,
            unknowns=unknown_domains,
            questions=questions,
            reassessment_triggers=(
                "Mudança material de exposição, correlação, alavancagem, margem ou drawdown.",
                "Aumento de spread, slippage, custos, volatilidade ou redução de liquidez.",
                "Falha, atraso, divergência ou perda de qualidade dos dados.",
                "Resultado de execução inesperado, estado de posição desconhecido ou reconciliação pendente.",
                "Evento de mercado ou operacional que torne as premissas anteriores inadequadas.",
            ),
            execution_authorized=False,
        )

    @staticmethod
    def _normalize_observations(values: Iterable[RiskObservation]) -> tuple[RiskObservation, ...]:
        result: list[RiskObservation] = []
        seen: set[RiskDomain] = set()
        for item in values:
            if not isinstance(item, RiskObservation):
                raise ValueError("observations must contain RiskObservation values")
            if item.domain in seen:
                continue
            if not isinstance(item.statement, str) or not item.statement.strip():
                raise ValueError("every risk observation requires a statement")
            if not isinstance(item.known, bool):
                raise ValueError("risk observation known must be boolean")
            result.append(
                RiskObservation(
                    domain=item.domain,
                    statement=item.statement.strip(),
                    known=item.known,
                    evidence=tuple(item.evidence),
                )
            )
            seen.add(item.domain)
        return tuple(result)

    @staticmethod
    def _normalize_domains(values: Iterable[RiskDomain]) -> tuple[RiskDomain, ...]:
        result: list[RiskDomain] = []
        for value in values:
            if not isinstance(value, RiskDomain):
                raise ValueError("available_domains must contain RiskDomain values")
            if value not in result:
                result.append(value)
        return tuple(result)

    @staticmethod
    def _questions(domains: Iterable[RiskDomain]) -> tuple[str, ...]:
        questions: list[str] = []
        for domain in domains:
            questions.append({
                RiskDomain.CAPITAL: "Quanto capital está efetivamente exposto e o que permanece disponível para absorver perdas?",
                RiskDomain.POSITION: "O tamanho e a estrutura da posição são conhecidos e compatíveis com o risco assumido?",
                RiskDomain.DRAWDOWN: "Qual é o drawdown atual e como ele altera a capacidade de assumir novo risco?",
                RiskDomain.LEVERAGE_MARGIN: "Qual é a alavancagem e a margem efetivamente utilizada, e o que acontece sob estresse?",
                RiskDomain.CONCENTRATION: "Existe concentração excessiva em um ativo, direção, estratégia ou fator?",
                RiskDomain.CORRELATION: "Posições aparentemente diferentes estão carregando o mesmo risco?",
                RiskDomain.LIQUIDITY: "A liquidez disponível é suficiente para entrar, sair e reduzir risco sem pressupor condições ideais?",
                RiskDomain.SLIPPAGE: "Quanto a execução pode se afastar do preço observado em condições normais e adversas?",
                RiskDomain.COSTS: "Spread, comissão, financiamento e outros custos alteram materialmente o resultado esperado?",
                RiskDomain.VOLATILITY: "A volatilidade atual muda a distribuição de resultados e o risco de movimentos adversos?",
                RiskDomain.GAP_EVENT: "Há possibilidade de gap, evento ou movimento descontínuo que invalide uma premissa de execução?",
                RiskDomain.MARKET_REGIME: "O regime de mercado atual é compatível com as premissas usadas para avaliar o risco?",
                RiskDomain.MODEL_UNCERTAINTY: "O que pode estar errado na interpretação ou no modelo e qual seria a evidência contrária?",
                RiskDomain.DATA_QUALITY: "Os dados são completos, atuais, consistentes e confiáveis para esta avaliação?",
                RiskDomain.EXECUTION: "A execução pode falhar, atrasar, duplicar ou retornar um estado que ainda não foi reconciliado?",
                RiskDomain.COUNTERPARTY: "Existem riscos relevantes do provedor, corretora, infraestrutura ou contraparte?",
                RiskDomain.OPERATIONAL: "Há alguma dependência operacional que possa impedir proteção, monitoramento ou encerramento?",
                RiskDomain.SECURITY: "Credenciais, permissões, integrações e dados estão protegidos contra uso indevido ou comprometimento?",
                RiskDomain.RECOVERY: "Se algo falhar, o sistema consegue parar com segurança, reconciliar o estado e recuperar sem assumir fatos desconhecidos?",
            }[domain])
        return tuple(questions)
