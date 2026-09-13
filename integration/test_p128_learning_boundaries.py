import pytest

from integration.ecosystem_service import EcosystemService


def test_external_learning_resource_starts_quarantined():
    service = EcosystemService()
    resource = service.add_learning_resource({
        "resource_id": "video-1",
        "title": "Material de estudo",
        "content_type": "VIDEO",
        "source_url": "https://example.com/video",
    })

    assert resource.resource_id == "video-1"
    assert service.learning_sources["video-1"].status.value == "QUARANTINED"
    assert service.learning_sources["video-1"].operation_eligible is False


def test_external_learning_knowledge_cannot_be_marked_validated_before_gate():
    service = EcosystemService()
    service.add_learning_resource({
        "resource_id": "doc-1",
        "title": "Documento",
        "content_type": "DOCUMENT",
        "source_url": "https://example.com/doc",
    })

    with pytest.raises(ValueError, match="external learning knowledge"):
        service.add_learning_observation({
            "resource_id": "doc-1",
            "statement": "Uma afirmação de mercado",
            "validated": True,
        })


def test_source_validation_and_knowledge_admission_still_never_make_operation_eligible():
    service = EcosystemService()
    service.add_learning_resource({
        "resource_id": "link-1",
        "title": "Fonte",
        "content_type": "ARTICLE",
        "source_url": "https://example.com/article",
    })
    source = service.learning_sources["link-1"]
    source = service.validate_learning_source(source, content_verified=True, security_checked=True)
    source = service.admit_learning_knowledge(source, knowledge_validated=True)

    assert source.status.value == "VALIDATED"
    assert source.knowledge_validated is True
    assert source.operation_eligible is False

    observation = service.add_learning_observation({
        "resource_id": "link-1",
        "statement": "Afirmação que passou pelo fluxo educacional",
        "validated": True,
    })
    assert observation.validated is True


def test_professor_activity_requires_validated_knowledge_and_is_not_trade_authority():
    service = EcosystemService()
    with pytest.raises(ValueError, match="validated knowledge"):
        service.generate_professor_activity({
            "activity_id": "quiz-1",
            "knowledge_id": "k-1",
            "statement": "Afirmação",
            "concept": "contexto",
            "knowledge_validated": False,
        })

    activity = service.generate_professor_activity({
        "activity_id": "quiz-2",
        "knowledge_id": "k-2",
        "statement": "Afirmação validada",
        "concept": "contexto",
        "knowledge_validated": True,
    })
    assert activity.activity_id == "quiz-2"
    assert service.learning_summary()["learning_authorizes_trading"] is False
