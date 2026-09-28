from __future__ import annotations

from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.p47_automation_closure import AutomationClosure
from core.p128_learning_handoff import OperationLearningHandoff
from execution.icmarkets_mt5_demo_outcome import MT5OutcomeEvidence
from integration.p139_post_demo_learning import PostDemoLearningBoundary, PostDemoLearningResult


class MT5PostDemoLearningBridge:
    """Connects verified MT5 financial evidence to the existing P139 boundary.

    The broker adapter creates facts. P139 remains the only owner of
    reconciliation/learning progression.
    """

    def __init__(self, *, post_demo: PostDemoLearningBoundary | None = None) -> None:
        self.post_demo = post_demo or PostDemoLearningBoundary()

    def process(
        self,
        *,
        evidence: MT5OutcomeEvidence,
        closure: AutomationClosure,
        analysis: AnalysisResult,
        market_context: MarketContextResult,
        note_id: str,
        what_happened: str,
        why_assessment: str,
        evidence_notes: tuple[str, ...] = (),
        lessons: tuple[str, ...] = (),
    ) -> PostDemoLearningResult:
        if not isinstance(evidence, MT5OutcomeEvidence):
            raise ValueError("MT5 outcome evidence inválida.")
        if not isinstance(closure, AutomationClosure):
            raise ValueError("automation closure inválida.")
        if evidence.cycle_id != closure.cycle_id:
            raise ValueError("cycle_id da evidência não corresponde ao fechamento.")
        if not isinstance(evidence.financial_result, float):
            raise ValueError("financial_result factual inválido.")

        return self.post_demo.process(
            closure=closure,
            observed_at=evidence.observed_at,
            outcome=evidence.outcome,
            financial_result=evidence.financial_result,
            external_observation=evidence.as_observation(),
            analysis=analysis,
            market_context=market_context,
            note_id=note_id,
            what_happened=what_happened,
            why_assessment=why_assessment,
            evidence=evidence_notes + (
                f"MT5 position_id={evidence.position_id}",
                f"MT5 close_external_id={evidence.close_external_id}",
                f"MT5 deal_ids={','.join(evidence.deal_ids)}",
            ),
            lessons=lessons,
        )
