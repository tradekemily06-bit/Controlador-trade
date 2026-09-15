from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .learning_material_review import EffectivenessVerdict, MaterialVerdict
from .p128_learning_professor import AnswerAssessment, LearningProfessor, ProfessorActivitySpec, QuizPlan
from .p128_learning_source_gate import LearningSourceStatus
from .professional_learning_question_engine import ProfessionalLearningQuestion
from .scoped_learning_state import LearningScope


class ScopedProfessorAssessment:
    """Security boundary between tenant learning state and the senior professor.

    Browser/API payloads may select an existing knowledge id, but they cannot
    supply the statement, concept, validation state, or assessment history.
    Those values are derived from the current trusted tenant's persisted scope.
    """

    def __init__(self, professor: LearningProfessor | None = None) -> None:
        self.professor = professor or LearningProfessor()

    @staticmethod
    def _validated_observation(scope: LearningScope, knowledge_id: str):
        key = str(knowledge_id).strip()
        source = scope.sources.get(key)
        if (
            source is None
            or source.status is not LearningSourceStatus.VALIDATED
            or not source.knowledge_validated
            or source.operation_eligible
        ):
            raise ValueError("only validated knowledge from the current tenant can be assessed")
        candidates = [
            item for item in scope.observations
            if item.resource_id == key and item.validated and item.statement.strip()
        ]
        if not candidates:
            raise ValueError("validated knowledge from the current tenant has no validated observation")
        # The latest stored observation is the authoritative educational
        # statement. Client-supplied text is never used to replace it.
        return candidates[-1]

    @staticmethod
    def _review_context(scope: LearningScope, knowledge_id: str) -> tuple[bool, int, str]:
        review = scope.material_reviews.get(str(knowledge_id).strip())
        if review is None:
            return False, 0, ""
        contradictions = sum(1 for claim in review.claims if claim.verdict is MaterialVerdict.CONTRADICTED)
        context_parts: list[str] = []
        if review.effectiveness.verdict is EffectivenessVerdict.NOT_ESTABLISHED:
            context_parts.append("A eficácia operacional do material não está estabelecida; trate-a como hipótese a testar, não como fato.")
        elif review.effectiveness.verdict is EffectivenessVerdict.MIXED:
            context_parts.append("A evidência de eficácia é mista; procure condições em que o resultado muda.")
        elif review.effectiveness.verdict is EffectivenessVerdict.SUPPORTED:
            context_parts.append("Há evidência de eficácia apoiando o material, mas valide contexto, amostra e limites.")
        if contradictions:
            context_parts.append(f"Há {contradictions} afirmação(ões) explicitamente contradita(s) pelo conhecimento revisado.")
        if review.limitations:
            context_parts.extend(review.limitations)
        return True, contradictions, " ".join(context_parts)

    def build_adaptive_quiz(
        self,
        scope: LearningScope,
        *,
        activity_id: str,
        knowledge_id: str,
        confidence: float | None = None,
        objective: str = "",
    ) -> tuple[QuizPlan, tuple[ProfessionalLearningQuestion, ...]]:
        observation = self._validated_observation(scope, knowledge_id)
        activity = scope.activities.get(str(activity_id).strip())
        if activity is None:
            raise ValueError("activity_id não encontrado no tenant atual")
        expected_knowledge = str(knowledge_id).strip()
        if expected_knowledge not in activity.expected_concepts:
            raise ValueError("activity is not bound to the requested validated knowledge")

        attempts = [item for item in scope.attempts if item.activity_id == activity.activity_id]
        prior_attempts = len(attempts)
        recent_gap_count = sum(1 for item in attempts[-5:] if item.correct is False)
        reviewed, contradictions, review_context = self._review_context(scope, expected_knowledge)
        spec = ProfessorActivitySpec(
            activity_id=activity.activity_id,
            knowledge_id=expected_knowledge,
            statement=observation.statement,
            concept=observation.concepts[0] if observation.concepts else "raciocínio de mercado",
            difficulty=activity.difficulty,
        )
        return self.professor.build_adaptive_quiz(
            spec,
            knowledge_validated=True,
            prior_attempts=prior_attempts,
            recent_gap_count=recent_gap_count,
            confidence=confidence,
            material_reviewed=reviewed,
            material_contradictions=contradictions,
            objective=objective,
            context=review_context,
        )

    def grade_and_record(
        self,
        scope: LearningScope,
        *,
        question: ProfessionalLearningQuestion,
        answer: str,
    ) -> AnswerAssessment:
        assessment = self.professor.grade_answer(question=question, answer=answer)
        # LearningAttempt remains the durable event format. Keep the detailed
        # professional result in feedback so the existing storage contract stays
        # backward compatible while remediation can count failed attempts.
        from .learning_content import LearningAttempt

        feedback = {
            "assessment": asdict(assessment),
            "question_id": question.question_id,
            "result": assessment.result,
        }
        import json
        scope.attempts.append(
            LearningAttempt(
                activity_id=question.question_id,
                answer=answer,
                correct=assessment.result == "STRONG",
                feedback=json.dumps(feedback, ensure_ascii=False, sort_keys=True),
            )
        )
        return assessment
