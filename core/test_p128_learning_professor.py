import pytest

from core.learning_content import LearningActivity
from core.p128_learning_professor import LearningProfessor, ProfessorActivitySpec


def test_professor_generates_activity_only_from_validated_knowledge():
    professor = LearningProfessor()
    spec = ProfessorActivitySpec(
        "quiz-validated-1",
        "knowledge-1",
        "Uma relação observada precisa ser avaliada no contexto.",
        "contexto",
    )

    activity = professor.build_activity(spec, knowledge_validated=True)

    assert isinstance(activity, LearningActivity)
    assert activity.activity_id == "quiz-validated-1"
    assert "knowledge-1" in activity.expected_concepts
    assert "contexto" in activity.prompt.lower()


def test_professor_rejects_unvalidated_knowledge():
    professor = LearningProfessor()
    spec = ProfessorActivitySpec("quiz-1", "knowledge-1", "Afirmação", "conceito")

    with pytest.raises(ValueError, match="validated knowledge"):
        professor.build_activity(spec, knowledge_validated=False)


def test_quiz_result_never_grants_trading_authority():
    professor = LearningProfessor()
    spec = ProfessorActivitySpec("quiz-2", "knowledge-2", "Afirmação validada", "conceito")
    activity = professor.build_activity(spec, knowledge_validated=True)

    correct, feedback = professor.grade_attempt(
        activity=activity,
        answer="Minha resposta com contexto e evidências.",
        evidence_based=True,
    )

    assert correct is True
    assert feedback
    assert not hasattr(activity, "execution_authorized")
