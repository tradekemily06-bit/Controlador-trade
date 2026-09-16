from core.p128_learning_professor import LearningProfessor, ProfessorActivitySpec
from core.professional_learning_question_engine import QuestionType


def test_professor_generates_deep_questions_from_validated_knowledge():
    professor = LearningProfessor()
    spec = ProfessorActivitySpec(
        activity_id="activity-1",
        knowledge_id="knowledge-market-structure",
        statement="Um rompimento deve ser interpretado no contexto da estrutura e da reação posterior.",
        concept="rompimento",
    )
    questions = professor.build_professional_questions(spec, knowledge_validated=True)
    assert len(questions) >= 9
    assert QuestionType.RISK in {q.question_type for q in questions}
    assert QuestionType.STATISTICAL_VALIDATION in {q.question_type for q in questions}
    assert QuestionType.SELF_CRITIQUE in {q.question_type for q in questions}


def test_professor_cannot_generate_questions_from_unvalidated_external_knowledge():
    professor = LearningProfessor()
    spec = ProfessorActivitySpec("activity-2", "external-video", "Afirmação", "conceito")
    try:
        professor.build_professional_questions(spec, knowledge_validated=False)
        assert False, "unvalidated knowledge must be rejected"
    except ValueError as exc:
        assert "validated knowledge" in str(exc)
