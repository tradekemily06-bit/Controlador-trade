from __future__ import annotations

from dataclasses import dataclass

from .learning_content import LearningActivity
from .professional_learning_question_engine import ProfessionalLearningQuestion, ProfessionalLearningQuestionEngine, QuestionType


@dataclass(frozen=True)
class ProfessorActivitySpec:
    """Educational activity generated only from validated knowledge."""

    activity_id: str
    knowledge_id: str
    statement: str
    concept: str
    difficulty: str = "INTERMEDIATE"

    def __post_init__(self) -> None:
        if not self.activity_id.strip() or not self.knowledge_id.strip():
            raise ValueError("activity_id and knowledge_id are required")
        if not self.statement.strip() or not self.concept.strip():
            raise ValueError("statement and concept are required")


class LearningProfessor:
    """Senior-teacher boundary for validated market knowledge.

    The professor may explain validated knowledge and create professional
    assessments from it, but it never treats a lesson, quiz, or user score as
    authorization to trade.
    """

    def __init__(self, question_engine: ProfessionalLearningQuestionEngine | None = None) -> None:
        self.question_engine = question_engine or ProfessionalLearningQuestionEngine()

    def build_activity(self, spec: ProfessorActivitySpec, *, knowledge_validated: bool) -> LearningActivity:
        if not isinstance(spec, ProfessorActivitySpec):
            raise ValueError("invalid professor activity specification")
        if not knowledge_validated:
            raise ValueError("only validated knowledge can generate operational teaching activities")
        return LearningActivity(
            activity_id=spec.activity_id,
            prompt=(
                f"Analise a afirmação validada a seguir e explique em qual contexto ela faz sentido, "
                f"quais evidências a sustentam e quais evidências poderiam contradizê-la: {spec.statement}"
            ),
            expected_concepts=(spec.concept, spec.knowledge_id),
            difficulty=spec.difficulty,
        )

    def build_professional_questions(self, spec: ProfessorActivitySpec, *, knowledge_validated: bool, context: str = "", question_types: tuple[QuestionType, ...] | None = None) -> tuple[ProfessionalLearningQuestion, ...]:
        if not isinstance(spec, ProfessorActivitySpec):
            raise ValueError("invalid professor activity specification")
        if not knowledge_validated:
            raise ValueError("only validated knowledge can generate professional questions")
        return self.question_engine.build(
            knowledge_id=spec.knowledge_id,
            concept=spec.concept,
            statement=spec.statement,
            context=context,
            question_types=question_types,
        )

    @staticmethod
    def grade_attempt(*, activity: LearningActivity, answer: str, evidence_based: bool) -> tuple[bool | None, str]:
        if not isinstance(activity, LearningActivity):
            raise ValueError("invalid learning activity")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("answer is required")
        if evidence_based:
            return True, "Resposta aceita: a análise considera contexto e evidências, não uma regra isolada."
        return False, "Reveja contexto, evidências favoráveis e contraevidências antes de concluir."
