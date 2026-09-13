"""Bridge senior risk reasoning with the existing operational RiskManager.

The senior layer answers whether the relevant risk domains were assessed;
the operational RiskManager answers whether configured operational limits
currently allow execution. Neither layer grants authority by itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from .risk_manager import RiskDecision
from .senior_risk_reasoning import RiskKnowledgeStatus, SeniorRiskAssessment


@dataclass(frozen=True)
class SeniorRiskGateDecision:
    allowed: bool
    reason: str


class SeniorRiskGate:
    """Require both senior risk completeness and operational risk approval."""

    def evaluate(
        self,
        *,
        senior_risk: SeniorRiskAssessment | None,
        operational_risk: RiskDecision,
    ) -> SeniorRiskGateDecision:
        if senior_risk is None:
            return SeniorRiskGateDecision(False, "Avaliação sênior de risco indisponível.")
        if not isinstance(senior_risk, SeniorRiskAssessment):
            return SeniorRiskGateDecision(False, "Avaliação sênior de risco inválida.")
        if senior_risk.execution_authorized:
            return SeniorRiskGateDecision(False, "A avaliação sênior de risco não pode conceder autoridade de execução.")
        if senior_risk.status is not RiskKnowledgeStatus.ASSESSED:
            return SeniorRiskGateDecision(False, "Risco sênior incompleto ou requer reavaliação.")
        if not isinstance(operational_risk, RiskDecision):
            return SeniorRiskGateDecision(False, "Decisão operacional de risco inválida.")
        if not operational_risk.allowed:
            return SeniorRiskGateDecision(False, operational_risk.reason)
        return SeniorRiskGateDecision(True, "Risco sênior e limites operacionais aprovados.")
