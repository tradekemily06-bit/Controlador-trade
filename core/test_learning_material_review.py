from core.learning_material_review import (
    EffectivenessVerdict,
    KnowledgeReference,
    LearningMaterialReviewer,
    MaterialEffectivenessReview,
    MaterialVerdict,
)


def test_unverified_video_or_link_never_becomes_knowledge():
    result = LearningMaterialReviewer().review(
        resource_id="video-1",
        claims=["Uma estratégia funciona sempre"],
        material_content_verified=False,
    )
    assert result.overall_verdict is MaterialVerdict.UNVERIFIED
    assert result.knowledge_level is MaterialVerdict.UNVERIFIED
    assert result.operation_authorized is False
    assert result.effectiveness.verdict is EffectivenessVerdict.NOT_ASSESSABLE


def test_verified_material_can_match_reviewed_knowledge():
    result = LearningMaterialReviewer().review(
        resource_id="link-1",
        claims=["Risco e tamanho da posição devem ser controlados"],
        references=[KnowledgeReference("risk-1", "Risco e tamanho da posição devem ser controlados", ("risk",))],
        material_content_verified=True,
    )
    assert result.overall_verdict is MaterialVerdict.KNOWN
    assert result.claims[0].verdict is MaterialVerdict.KNOWN
    assert result.claims[0].confidence == 1.0
    assert result.operation_authorized is False


def test_effectiveness_is_separate_from_conceptual_correctness():
    result = LearningMaterialReviewer().review(
        resource_id="video-2",
        claims=["Uma entrada baseada em pullback pode ser usada como hipótese"],
        references=[KnowledgeReference("pullback-1", "Uma entrada baseada em pullback pode ser usada como hipótese")],
        effectiveness=MaterialEffectivenessReview(
            EffectivenessVerdict.SUPPORTED,
            "Resultado sustentado pelo conjunto de testes informado.",
            sample_size=500,
            tested_period="2025-2026",
        ),
        material_content_verified=True,
    )
    assert result.overall_verdict is MaterialVerdict.KNOWN
    assert result.effectiveness.verdict is EffectivenessVerdict.SUPPORTED
    assert result.effectiveness.sample_size == 500
    assert result.operation_authorized is False
