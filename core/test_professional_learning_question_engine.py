from core.professional_learning_question_engine import ProfessionalLearningQuestionEngine, QuestionType


def test_engine_generates_professional_questions_beyond_recall():
    questions = ProfessionalLearningQuestionEngine().build(
        knowledge_id="senior-structure",
        concept="rompimento e pullback",
        statement="um rompimento pode ser confirmado pelo comportamento posterior do preço",
    )
    kinds = {item.question_type for item in questions}
    assert QuestionType.CONTEXT in kinds
    assert QuestionType.COUNTERFACTUAL in kinds
    assert QuestionType.STATISTICAL_VALIDATION in kinds
    assert QuestionType.RISK in kinds
    assert all(item.source_basis == ("senior-structure", "rompimento e pullback") for item in questions)


def test_engine_can_focus_a_professional_assessment():
    questions = ProfessionalLearningQuestionEngine().build(
        knowledge_id="risk-1",
        concept="position sizing",
        statement="o tamanho da posição deve respeitar o risco máximo definido",
        question_types=(QuestionType.RISK, QuestionType.STATISTICAL_VALIDATION, QuestionType.SELF_CRITIQUE),
    )
    assert [item.question_type for item in questions] == [QuestionType.RISK, QuestionType.STATISTICAL_VALIDATION, QuestionType.SELF_CRITIQUE]
    assert all(item.difficulty == "ADVANCED" for item in questions)
