from __future__ import annotations

from dataclasses import dataclass

from .professional_learning_question_engine import ProfessionalLearningQuestion, ProfessionalLearningQuestionEngine, QuestionType


@dataclass(frozen=True)
class SeniorQuestionProfile:
    """Question dimensions used by the educational layer."""

    concept: str
    statement: str
    context: str = ""
    knowledge_id: str = "senior-knowledge"


class SeniorQuestionBank:
    """Builds varied professional assessments from the ecosystem's knowledge.

    The bank intentionally avoids a fixed small quiz. A curriculum can request
    all dimensions or select a subset appropriate to the learner's stage.
    """

    DEFAULT_TYPES = (
        QuestionType.CONTEXT,
        QuestionType.SCENARIO,
        QuestionType.COUNTERFACTUAL,
        QuestionType.EVIDENCE,
        QuestionType.RISK,
        QuestionType.EXECUTION_DISCIPLINE,
        QuestionType.STATISTICAL_VALIDATION,
        QuestionType.MARKET_STRUCTURE,
        QuestionType.SELF_CRITIQUE,
    )

    def __init__(self, engine: ProfessionalLearningQuestionEngine | None = None) -> None:
        self.engine = engine or ProfessionalLearningQuestionEngine()

    def generate(self, profile: SeniorQuestionProfile, *, types: tuple[QuestionType, ...] | None = None) -> tuple[ProfessionalLearningQuestion, ...]:
        if not isinstance(profile, SeniorQuestionProfile):
            raise ValueError("profile must be SeniorQuestionProfile")
        return self.engine.build(
            knowledge_id=profile.knowledge_id,
            concept=profile.concept,
            statement=profile.statement,
            context=profile.context,
            question_types=types or self.DEFAULT_TYPES,
        )
