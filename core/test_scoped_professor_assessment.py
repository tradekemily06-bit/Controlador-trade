import pytest

from core.learning_content import LearningActivity, LearningObservation, LearningAttempt
from core.learning_material_review import (
    EffectivenessVerdict,
    KnowledgeReference,
    LearningMaterialReviewer,
    MaterialEffectivenessReview,
    MaterialVerdict,
)
from core.p128_learning_source_gate import LearningSource, LearningSourceStatus, LearningSourceType
from core.scoped_learning_state import LearningScope
from core.scoped_professor_assessment import ScopedProfessorAssessment


def _scope() -> LearningScope:
    scope = LearningScope()
    scope.sources["k-1"] = LearningSource(
        source_id="k-1",
        source_type=LearningSourceType.LINK,
        uri="https://example.com/knowledge",
        status=LearningSourceStatus.VALIDATED,
        content_verified=True,
        security_checked=True,
        knowledge_validated=True,
        operation_eligible=False,
    )
    scope.observations.append(
        LearningObservation(
            resource_id="k-1",
            statement="Uma estrutura de mercado deve ser avaliada no contexto e confirmada por evidência.",
            concepts=("estrutura de mercado", "evidência"),
            validated=True,
        )
    )
    scope.activities["activity-1"] = LearningActivity(
        activity_id="activity-1",
        prompt="Avalie a estrutura.",
        expected_concepts=("estrutura de mercado", "k-1"),
        difficulty="ADVANCED",
    )
    return scope


def test_professor_uses_stored_validated_observation_not_browser_statement():
    scope = _scope()
    service = ScopedProfessorAssessment()

    plan, questions = service.build_adaptive_quiz(
        scope,
        activity_id="activity-1",
        knowledge_id="k-1",
    )

    assert plan.mode.value == "DIAGNOSTIC"
    assert questions
    assert all("estrutura de mercado" in q.prompt.lower() or "evidência" in q.prompt.lower() for q in questions)


def test_unvalidated_source_or_missing_validated_observation_is_blocked():
    scope = _scope()
    scope.sources["k-1"] = LearningSource(
        source_id="k-1",
        source_type=LearningSourceType.LINK,
        uri="https://example.com/knowledge",
        status=LearningSourceStatus.QUARANTINED,
    )

    with pytest.raises(ValueError, match="validated knowledge"):
        ScopedProfessorAssessment().build_adaptive_quiz(
            scope,
            activity_id="activity-1",
            knowledge_id="k-1",
        )


def test_material_contradictions_change_assessment_mode_and_context():
    scope = _scope()
    review = LearningMaterialReviewer().review(
        resource_id="k-1",
        claims=["A estrutura sempre funciona sem considerar contexto."],
        references=[KnowledgeReference("ref-1", "A estrutura deve ser avaliada no contexto e confirmada por evidência.")],
        contradicted_claims={"A estrutura sempre funciona sem considerar contexto": ["ref-1"]},
        effectiveness=MaterialEffectivenessReview(
            EffectivenessVerdict.NOT_ESTABLISHED,
            "Amostra insuficiente.",
        ),
        material_content_verified=True,
    )
    scope.material_reviews["k-1"] = review
    scope.attempts.append(LearningAttempt(activity_id="activity-1", answer="resposta anterior", correct=True))

    plan, questions = ScopedProfessorAssessment().build_adaptive_quiz(
        scope,
        activity_id="activity-1",
        knowledge_id="k-1",
    )

    assert plan.mode.value == "MATERIAL_REVIEW"
    assert any("contra" in q.prompt.lower() or "evid" in q.prompt.lower() for q in questions)


def test_grading_is_recorded_against_activity_for_future_remediation():
    scope = _scope()
    service = ScopedProfessorAssessment()
    _, questions = service.build_adaptive_quiz(scope, activity_id="activity-1", knowledge_id="k-1")

    assessment = service.grade_and_record(
        scope,
        activity_id="activity-1",
        question=questions[0],
        answer="Contexto, evidência, invalidação e risco precisam ser avaliados antes de concluir domínio.",
    )

    assert assessment.trading_authorized is False
    assert scope.attempts[-1].activity_id == "activity-1"
    assert scope.attempts[-1].feedback
