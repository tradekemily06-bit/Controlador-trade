"""Advanced, non-diagnostic trading-psychology analysis.

This module studies observable trading behavior and self-reported state. It is
an educational/risk-awareness layer: it can recommend a pause or review, but
it can never authorize an order or replace the risk/execution gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean
from typing import Iterable


class BehavioralPattern(str, Enum):
    FOMO = "FOMO"
    REVENGE = "REVENGE"
    OVERTRADING = "OVERTRADING"
    RISK_ESCALATION = "RISK_ESCALATION"
    LOSS_CHASING = "LOSS_CHASING"
    OVERCONFIDENCE = "OVERCONFIDENCE"
    FEAR_AVOIDANCE = "FEAR_AVOIDANCE"
    RULE_BREAKING = "RULE_BREAKING"
    TILT = "TILT"
    FATIGUE = "FATIGUE"
    IMPATIENCE = "IMPATIENCE"
    RECENCY_BIAS = "RECENCY_BIAS"
    CONFIRMATION_SEEKING = "CONFIRMATION_SEEKING"
    LOSS_AVERSION = "LOSS_AVERSION"


@dataclass(frozen=True)
class TradingBehaviorSnapshot:
    """Observable facts from a trading session; no diagnosis is implied."""

    trades_count: int = 0
    losses: int = 0
    wins: int = 0
    consecutive_losses: int = 0
    avg_seconds_between_trades: float | None = None
    risk_before: float | None = None
    risk_after: float | None = None
    rule_breaks: int = 0
    impulsive_entries: int = 0
    avoided_valid_setups: int = 0
    repeated_entries_after_loss: int = 0
    confirmation_requests: int = 0
    fatigue: int = 0
    urge_to_trade: int = 0
    confidence: int = 0
    emotional_state: str = ""


@dataclass(frozen=True)
class BehavioralEvidence:
    pattern: BehavioralPattern
    severity: int
    evidence: tuple[str, ...]
    recommendation: str


@dataclass(frozen=True)
class PsychologyTrend:
    sessions: int
    average_risk_score: float
    high_risk_sessions: int
    recurring_patterns: tuple[BehavioralPattern, ...]
    direction: str


@dataclass(frozen=True)
class AdvancedPsychologyAssessment:
    score: int
    risk_level: str
    evidence: tuple[BehavioralEvidence, ...]
    recommendations: tuple[str, ...]
    trend: PsychologyTrend | None = None
    trading_authorized: bool = False


class AdvancedTradingPsychology:
    """Detect recurring behavioral risk without becoming an execution authority."""

    def _validate(self, s: TradingBehaviorSnapshot) -> None:
        for name in ("trades_count", "losses", "wins", "consecutive_losses", "rule_breaks", "impulsive_entries", "avoided_valid_setups", "repeated_entries_after_loss", "confirmation_requests"):
            if not isinstance(getattr(s, name), int) or getattr(s, name) < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in ("fatigue", "urge_to_trade", "confidence"):
            value = getattr(s, name)
            if not isinstance(value, int) or not 0 <= value <= 10:
                raise ValueError(f"{name} must be an integer from 0 to 10")
        if s.risk_before is not None and s.risk_before < 0:
            raise ValueError("risk_before must be non-negative")
        if s.risk_after is not None and s.risk_after < 0:
            raise ValueError("risk_after must be non-negative")
        if s.avg_seconds_between_trades is not None and s.avg_seconds_between_trades < 0:
            raise ValueError("avg_seconds_between_trades must be non-negative")

    def assess(self, snapshot: TradingBehaviorSnapshot) -> AdvancedPsychologyAssessment:
        self._validate(snapshot)
        found: list[BehavioralEvidence] = []

        def add(pattern: BehavioralPattern, severity: int, *evidence: str, recommendation: str) -> None:
            found.append(BehavioralEvidence(pattern, max(1, min(10, severity)), tuple(evidence), recommendation))

        if snapshot.urge_to_trade >= 8 and snapshot.trades_count > 0:
            add(BehavioralPattern.FOMO, 8, "urgência de operar >= 8/10", recommendation="reduzir estímulos e esperar uma condição validada")
        if (snapshot.losses >= 2 or snapshot.consecutive_losses >= 3) and (snapshot.repeated_entries_after_loss > 0 or snapshot.consecutive_losses >= 2):
            add(BehavioralPattern.REVENGE, 9, "entradas repetidas após perda ou sequência de perdas", recommendation="pausar e revisar a regra de parada após perdas")
        if snapshot.trades_count >= 12:
            add(BehavioralPattern.OVERTRADING, 7, "volume elevado de operações na sessão", recommendation="comparar quantidade de entradas com o plano da sessão")
        if snapshot.risk_before is not None and snapshot.risk_after is not None and snapshot.risk_after > snapshot.risk_before * 1.25:
            add(BehavioralPattern.RISK_ESCALATION, 9, "risco posterior > 125% do risco inicial", recommendation="bloquear aumento discricionário de risco até revisão")
        if snapshot.losses > 0 and snapshot.trades_count > snapshot.wins + snapshot.losses:
            add(BehavioralPattern.LOSS_CHASING, 7, "atividade posterior às perdas sem correspondência no registro de resultado", recommendation="reconciliar operações antes de continuar")
        if snapshot.confidence >= 9 and snapshot.rule_breaks > 0:
            add(BehavioralPattern.OVERCONFIDENCE, 8, "confiança >= 9/10 com quebra de regra", recommendation="rebaixar confiança até voltar a cumprir o plano")
        if snapshot.avoided_valid_setups >= 3 and snapshot.emotional_state.strip().lower() in {"medo", "fear", "ansioso", "ansiedade"}:
            add(BehavioralPattern.FEAR_AVOIDANCE, 7, "setups válidos evitados repetidamente com estado de medo/ansiedade", recommendation="estudar as entradas evitadas sem forçar operação real")
        if snapshot.rule_breaks >= 2:
            add(BehavioralPattern.RULE_BREAKING, 9, "duas ou mais quebras de regra", recommendation="interromper a sessão e revisar as regras objetivas")
        if snapshot.rule_breaks >= 2 and snapshot.losses >= 2:
            add(BehavioralPattern.TILT, 10, "quebras de regra combinadas com perdas", recommendation="encerrar a sessão e registrar o gatilho comportamental")
        if snapshot.fatigue >= 7:
            add(BehavioralPattern.FATIGUE, 7, "fadiga >= 7/10", recommendation="reduzir carga cognitiva e considerar encerrar a sessão")
        if snapshot.avg_seconds_between_trades is not None and snapshot.avg_seconds_between_trades < 60 and snapshot.trades_count >= 5:
            add(BehavioralPattern.IMPATIENCE, 7, "intervalo médio entre entradas < 60 segundos", recommendation="exigir confirmação antes de uma nova entrada")
        if snapshot.consecutive_losses >= 3:
            add(BehavioralPattern.RECENCY_BIAS, 6, "sequência recente de três ou mais perdas", recommendation="não extrapolar o último resultado para a próxima decisão")
        if snapshot.confirmation_requests >= 3 and snapshot.trades_count > 0:
            add(BehavioralPattern.CONFIRMATION_SEEKING, 6, "múltiplas solicitações de confirmação na mesma sessão", recommendation="usar critérios previamente definidos em vez de buscar validação emocional")
        if snapshot.losses > 0 and snapshot.avoided_valid_setups > snapshot.wins:
            add(BehavioralPattern.LOSS_AVERSION, 6, "setups evitados superam operações vencedoras após perdas", recommendation="revisar a diferença entre cautela planejada e evasão por perda recente")

        unique: dict[BehavioralPattern, BehavioralEvidence] = {}
        for item in found:
            if item.pattern not in unique or item.severity > unique[item.pattern].severity:
                unique[item.pattern] = item
        evidence = tuple(unique.values())
        score = min(100, sum(item.severity for item in evidence) * 5)
        risk = "HIGH" if score >= 60 or any(item.severity >= 9 for item in evidence) else "MODERATE" if score >= 25 else "LOW"
        recommendations = tuple(dict.fromkeys(item.recommendation for item in evidence))
        if not recommendations:
            recommendations = ("seguir o plano objetivo e registrar o contexto da sessão",)
        return AdvancedPsychologyAssessment(score, risk, evidence, recommendations, trading_authorized=False)

    def trend(self, assessments: Iterable[AdvancedPsychologyAssessment]) -> PsychologyTrend:
        items = tuple(assessments)
        if not items:
            return PsychologyTrend(0, 0.0, 0, tuple(), "NO_DATA")
        avg = mean(item.score for item in items)
        high = sum(item.risk_level == "HIGH" for item in items)
        counts: dict[BehavioralPattern, int] = {}
        for assessment in items:
            for evidence in assessment.evidence:
                counts[evidence.pattern] = counts.get(evidence.pattern, 0) + 1
        recurring = tuple(pattern for pattern, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0].value)) if count >= 2)
        if len(items) >= 2:
            split = max(1, (len(items) + 1) // 2)
            first = mean(item.score for item in items[:split])
            second = mean(item.score for item in items[split:]) if items[split:] else items[-1].score
            direction = "WORSENING" if second > first + 5 else "IMPROVING" if second < first - 5 else "STABLE"
        else:
            direction = "INSUFFICIENT_HISTORY"
        return PsychologyTrend(len(items), round(avg, 2), high, recurring, direction)
