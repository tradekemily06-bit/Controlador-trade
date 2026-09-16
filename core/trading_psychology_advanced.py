"""Advanced trader-psychology analytics and behavioral guardrails.

This module treats trading psychology as an operational, educational layer.
It models observable trading behavior (not mental-health diagnoses), identifies
behavioral risk patterns, and produces explainable interventions. It can never
authorize execution and should not be used to infer clinical conditions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean
from typing import Iterable


class BehavioralPattern(str, Enum):
    FOMO = "FOMO"
    REVENGE_TRADING = "REVENGE_TRADING"
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
class BehavioralObservation:
    """One observable session/operation behavior; values are operational, not clinical."""

    operations: int = 0
    losses: int = 0
    consecutive_losses: int = 0
    seconds_since_last_operation: int | None = None
    risk_per_operation: float = 0.0
    baseline_risk: float = 0.0
    rules_broken: int = 0
    repeated_same_setup: int = 0
    hesitation_count: int = 0
    revenge_intent: bool = False
    urgency: int = 0
    fatigue: int = 0
    confidence: int = 5
    plan_adherence: int = 10
    post_loss_risk_change: float = 0.0
    recent_win_streak: int = 0
    recent_loss_streak: int = 0


@dataclass(frozen=True)
class PsychologyProfile:
    patterns: tuple[BehavioralPattern, ...]
    severity: str
    score: float
    evidence: tuple[str, ...]
    intervention: str
    learning_focus: tuple[str, ...]
    execution_authorized: bool = False


class AdvancedTradingPsychology:
    """Explainable behavioral risk engine; execution authorization is always false."""

    def assess(self, observation: BehavioralObservation) -> PsychologyProfile:
        self._validate(observation)
        patterns: list[BehavioralPattern] = []
        evidence: list[str] = []
        focus: list[str] = []

        if observation.revenge_intent or (observation.recent_loss_streak >= 2 and observation.urgency >= 7):
            patterns.append(BehavioralPattern.REVENGE_TRADING)
            evidence.append("perdas recentes combinadas com urgência/intenção de recuperar")
            focus.append("separar resultado anterior da próxima decisão")
        if observation.urgency >= 8 and (observation.seconds_since_last_operation is None or observation.seconds_since_last_operation < 60):
            patterns.append(BehavioralPattern.FOMO)
            evidence.append("urgência elevada e entrada muito próxima da decisão anterior")
            focus.append("esperar o gatilho completo em vez de perseguir o movimento")
        if observation.operations >= 8:
            patterns.append(BehavioralPattern.OVERTRADING)
            evidence.append("frequência operacional elevada na sessão")
            focus.append("definir limite de qualidade, não apenas quantidade")
        if observation.baseline_risk > 0 and observation.risk_per_operation > observation.baseline_risk * 1.5:
            patterns.append(BehavioralPattern.RISK_ESCALATION)
            evidence.append("risco por operação aumentou significativamente sobre a linha de base")
            focus.append("manter risco estável após ganhos ou perdas")
        if observation.recent_loss_streak >= 3 and observation.post_loss_risk_change > 0:
            patterns.append(BehavioralPattern.LOSS_CHASING)
            evidence.append("aumento de risco após sequência de perdas")
            focus.append("interromper recuperação por aumento de lote")
        if observation.confidence >= 9 and observation.plan_adherence <= 5:
            patterns.append(BehavioralPattern.OVERCONFIDENCE)
            evidence.append("confiança muito alta com baixa aderência ao plano")
            focus.append("exigir evidência objetiva antes da decisão")
        if observation.hesitation_count >= 3 and observation.confidence <= 4:
            patterns.append(BehavioralPattern.FEAR_AVOIDANCE)
            evidence.append("hesitação repetida acompanhada de baixa confiança")
            focus.append("distinguir medo de uma invalidação objetiva do setup")
        if observation.rules_broken >= 1 or observation.plan_adherence <= 4:
            patterns.append(BehavioralPattern.RULE_BREAKING)
            evidence.append("regras/plano não foram seguidos")
            focus.append("registrar qual regra foi quebrada e por quê")
        if observation.rules_broken >= 2 and observation.urgency >= 7:
            patterns.append(BehavioralPattern.TILT)
            evidence.append("quebra de regras combinada com urgência")
            focus.append("pausar antes de uma nova decisão")
        if observation.fatigue >= 7:
            patterns.append(BehavioralPattern.FATIGUE)
            evidence.append("fadiga operacional elevada")
            focus.append("encerrar ou reduzir exposição quando a atenção deteriorar")
        if observation.seconds_since_last_operation is not None and observation.seconds_since_last_operation < 30:
            patterns.append(BehavioralPattern.IMPATIENCE)
            evidence.append("intervalo extremamente curto entre decisões")
            focus.append("não transformar velocidade em critério de entrada")
        if observation.recent_win_streak >= 3 and observation.confidence >= 8:
            patterns.append(BehavioralPattern.RECENCY_BIAS)
            evidence.append("sequência recente de ganhos pode estar elevando a confiança")
            focus.append("avaliar o setup atual sem usar a sequência passada como prova")
        if observation.repeated_same_setup >= 3 and observation.plan_adherence <= 6:
            patterns.append(BehavioralPattern.CONFIRMATION_SEEKING)
            evidence.append("repetição do mesmo setup apesar de baixa aderência")
            focus.append("procurar também evidências que invalidem a hipótese")
        if observation.hesitation_count >= 2 and observation.losses > 0:
            patterns.append(BehavioralPattern.LOSS_AVERSION)
            evidence.append("hesitação recorrente após resultados negativos")
            focus.append("separar qualidade da decisão de resultado isolado")

        patterns = list(dict.fromkeys(patterns))
        score = min(100.0, 100.0 * (1.0 - (len(patterns) / 8.0))) if patterns else 100.0
        if any(p in patterns for p in (BehavioralPattern.TILT, BehavioralPattern.LOSS_CHASING, BehavioralPattern.RISK_ESCALATION)):
            severity = "CRITICAL"
            intervention = "pausar operações e revisar o plano; nenhum componente desta camada libera execução"
        elif len(patterns) >= 3:
            severity = "HIGH"
            intervention = "reduzir atividade e revisar as regras antes da próxima decisão"
        elif patterns:
            severity = "MODERATE"
            intervention = "fazer uma pausa curta e confirmar o plano antes da próxima decisão"
        else:
            severity = "LOW"
            intervention = "seguir o plano e registrar a qualidade da decisão"

        return PsychologyProfile(tuple(patterns), severity, round(score, 2), tuple(evidence), intervention, tuple(dict.fromkeys(focus)), False)

    def session_trend(self, observations: Iterable[BehavioralObservation]) -> dict[str, object]:
        items = tuple(observations)
        if not items:
            return {"sessions": 0, "average_behavior_score": 100.0, "high_risk_sessions": 0, "recurring_patterns": [], "trend": "NO_DATA"}
        profiles = tuple(self.assess(item) for item in items)
        scores = [profile.score for profile in profiles]
        pattern_counts: dict[str, int] = {}
        for profile in profiles:
            for pattern in profile.patterns:
                pattern_counts[pattern.value] = pattern_counts.get(pattern.value, 0) + 1
        first_half = mean(scores[: max(1, len(scores) // 2)])
        second_half = mean(scores[max(1, len(scores) // 2):])
        if second_half > first_half + 5:
            trend = "IMPROVING"
        elif second_half < first_half - 5:
            trend = "DETERIORATING"
        else:
            trend = "STABLE"
        return {"sessions": len(items), "average_behavior_score": round(mean(scores), 2), "high_risk_sessions": sum(profile.severity in {"HIGH", "CRITICAL"} for profile in profiles), "recurring_patterns": sorted(pattern_counts, key=pattern_counts.get, reverse=True), "trend": trend}

    @staticmethod
    def _validate(observation: BehavioralObservation) -> None:
        integer_fields = (observation.operations, observation.losses, observation.consecutive_losses, observation.rules_broken, observation.repeated_same_setup, observation.hesitation_count, observation.urgency, observation.fatigue, observation.confidence, observation.plan_adherence, observation.recent_win_streak, observation.recent_loss_streak)
        if any(not isinstance(value, int) or value < 0 for value in integer_fields):
            raise ValueError("behavioral counters and scores must be non-negative integers")
        if any(value > 10 for value in (observation.urgency, observation.fatigue, observation.confidence, observation.plan_adherence)):
            raise ValueError("behavioral scores must be from 0 to 10")
        if observation.seconds_since_last_operation is not None and observation.seconds_since_last_operation < 0:
            raise ValueError("seconds_since_last_operation must be non-negative")
        if observation.risk_per_operation < 0 or observation.baseline_risk < 0:
            raise ValueError("risk values must be non-negative")
        if observation.post_loss_risk_change < -1:
            raise ValueError("post_loss_risk_change is outside supported range")
