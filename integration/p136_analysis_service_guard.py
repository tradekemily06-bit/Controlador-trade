from __future__ import annotations

from typing import Any, Mapping

from core.senior_context_cycle import SeniorContextCycle
from core.senior_risk_reasoning import RiskKnowledgeStatus
from .p135_senior_analysis_boundary import SeniorAnalysisBoundary


class AnalysisServiceGuard:
    """Application analysis gate: no score-only analysis may masquerade as senior analysis."""

    @staticmethod
    def require_senior_context(payload: Mapping[str, Any], context: SeniorContextCycle | None) -> SeniorContextCycle:
        if not isinstance(payload, Mapping):
            raise ValueError("analysis payload must be an object")
        if context is None:
            raise ValueError("senior context is required for application analysis")
        if not isinstance(context, SeniorContextCycle):
            raise ValueError("senior context is invalid")
        if context.execution_authorized:
            raise ValueError("senior context cannot authorize execution")
        if context.quality.value != "COMPLETE":
            raise ValueError("senior context is incomplete")
        if context.risk_assessment.status is not RiskKnowledgeStatus.ASSESSED:
            raise ValueError("senior risk assessment is not complete")
        return context

    @staticmethod
    def build_context(payload: Mapping[str, Any]) -> SeniorContextCycle:
        """Build context from explicit market/risk evidence before signal evaluation."""
        request = SeniorAnalysisBoundary.build_input(payload)
        from core.senior_context_orchestrator import SeniorContextOrchestrator
        return SeniorContextOrchestrator().assess(request)
