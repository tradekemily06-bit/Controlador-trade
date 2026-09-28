from __future__ import annotations

from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.p47_automation_closure import AutomationClosure
from core.p49_outcome_reconciliation import ExternalOutcomeObservation
from integration.p139_post_demo_learning import PostDemoLearningBoundary, PostDemoLearningResult


class PostExecutionLearningBridge:
    """Broker-neutral handoff from verified external facts to P139.

    The concrete broker/platform adapter is responsible for obtaining facts.
    This bridge deliberately knows nothing about MT5, cTrader, a broker, or a
    transport. P139 remains the owner of reconciliation/learning progression.
    """

    def __init__(self, *, post_demo: PostDemoLearningBoundary | None = None) -> None:
        self.post_demo = post_demo or PostDemoLearningBoundary()

    def process(
        self,
        *,
        evidence: ExternalOutcomeObservation,
        closure: AutomationClosure,
        analysis: AnalysisResult,
        market_context: MarketContextResult,
        note_id: str,
        what_happened: str,
        why_assessment: str,
        evidence_notes: tuple[str, ...] = (),
        lessons: tuple[str, ...] = (),
    ) -> PostDemoLearningResult:
        if not isinstance(evidence, ExternalOutcomeObservation):
            raise ValueError("evidência externa inválida.")
        if not isinstance(closure, AutomationClosure):
            raise ValueError("automation closure inválida.")
        if evidence.cycle_id != closure.cycle_id:
            raise ValueError("cycle_id da evidência não corresponde ao fechamento.")
        if not isinstance(evidence.financial_result, float):
            raise ValueError("financial_result factual inválido.")

        source_note = f"external_source={evidence.source or 'UNSPECIFIED'}"
        container_note = f"external_container_id={evidence.external_container_id or 'UNSPECIFIED'}"
        reference_note = f"external_reference={evidence.external_reference or 'UNSPECIFIED'}"
        result_note = f"external_result_ids={','.join(evidence.external_result_ids)}"

        return self.post_demo.process(
            closure=closure,
            observed_at=evidence.observed_at,
            outcome=evidence.outcome,
            financial_result=evidence.financial_result,
            external_observation=evidence,
            analysis=analysis,
            market_context=market_context,
            note_id=note_id,
            what_happened=what_happened,
            why_assessment=why_assessment,
            evidence=evidence_notes + (
                source_note,
                container_note,
                reference_note,
                result_note,
            ),
            lessons=lessons,
        )


# Backward-compatible name for existing DEMO callers. The contract itself is mode-neutral.
PostDemoLearningBridge = PostExecutionLearningBridge
