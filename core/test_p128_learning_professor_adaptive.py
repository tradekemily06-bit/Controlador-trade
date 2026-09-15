import pytest

from core.p128_learning_professor import LearningProfessor, ProfessorActivitySpec, QuizMode
from core.professional_learning_question_engine import QuestionType


@pytest.fixture
def spec() -> ProfessorActivitySpec:
    return ProfessorActivitySpec(
        activity_id="activity-1",
        knowledge_id="senior-structure",
        concept="rompimento e pullback",
        statement="um rompimento pode ser confirmado pelo comportamento posterior do preço",
    )


def test_professor_selects_diagnostic_depth_for_first_assessment(spec):
    plan = LearningProfessor().plan_quiz(spec, knowledge_validated=True)
    assert plan.mode is QuizMode.DIAGNOSTIC
    assert plan.question_count == 5
    assert QuestionType.CONTEXT in plan.question_types
    assert QuestionType.STATISTICAL_VALIDATION not in plan.question_types


def test_professor_expands_remediation_when_many_gaps_exist(spec):
    plan = LearningProfessor().plan_quiz(
        spec,
        knowledge_validated=True,
        prior_attempts=2,
        recent_gap_count=4,
    )
    assert plan.mode is QuizMode.REMEDIATION
    assert plan.question_count == 7
    assert QuestionType.STATISTICAL_VALIDATION in plan.question_types
    assert QuestionType.MARKET_STRUCTURE in plan.question_types


def test_professor_can_deepen_to_mastery_without_history_cap(spec):
    plan = LearningProfessor().plan_quiz(
        spec,
        knowledge_validated=True,
        prior_attempts=1000,
        confidence=0.95,
    )
    assert plan.mode is QuizMode.MASTERY
    assert plan.question_count == len(tuple(QuestionType))
    assert "confiança" in " ".join(plan.rationale)


def test_professor_blocks_unvalidated_knowledge(spec):
    with pytest.raises(ValueError):
        LearningProfessor().plan_quiz(spec, knowledge_validated=False)
    with pytest.raises(ValueError):
        LearningProfessor().build_adaptive_quiz(spec, knowledge_validated=False)


def test_professor_grading_identifies_missing_evidence(spec):
    question = LearningProfessor().build_professional_questions(
        spec,
        knowledge_validated=True,
        question_types=(QuestionType.RISK,),
    )[0]
    assessment = LearningProfessor.grade_answer(
        question=question,
        answer="Eu avaliaria o risco máximo, a invalidação e a exposição antes de decidir.",
    )
    assert assessment.result in {"PARTIAL", "STRONG"}
    assert assessment.score > 0
    assert assessment.trading_authorized is False
    assert assessment.gaps or assessment.strengths


def test_professor_never_grants_execution_authority(spec):
    plan, questions = LearningProfessor().build_adaptive_quiz(
        spec,
        knowledge_validated=True,
        material_reviewed=True,
        material_contradictions=2,
    )
    assert plan.mode is QuizMode.MATERIAL_REVIEW
    assert questions
    assessment = LearningProfessor.grade_answer(
        question=questions[0],
        answer="A evidência precisa ser comparada com a contraevidência e testada estatisticamente antes de qualquer conclusão.",
    )
    assert assessment.trading_authorized is False
