from core.ecosystem_state_store import EcosystemStateStore
from integration.ecosystem_service import EcosystemService


def test_learning_records_survive_service_restart_without_trading_authority(tmp_path):
    store = EcosystemStateStore(tmp_path / "ecosystem-state.sqlite")
    first = EcosystemService()
    first.state_store = store

    first.add_learning_resource({
        "resource_id": "resource-1",
        "title": "Estudo de tendência",
        "content_type": "ARTICLE",
        "source_url": "https://example.com/estudo",
        "tags": ["tendência", "price action"],
    })
    first.add_learning_observation({
        "resource_id": "resource-1",
        "statement": "A observação precisa de validação independente.",
        "concepts": ["tendência"],
        "validated": False,
    })
    first.add_learning_activity({
        "activity_id": "activity-1",
        "prompt": "Identifique a tendência no cenário.",
        "expected_concepts": ["tendência"],
    })
    first.add_learning_attempt({
        "activity_id": "activity-1",
        "answer": "Possível tendência de alta.",
        "correct": None,
        "feedback": "Aguardando avaliação.",
    })

    restored = EcosystemService()
    restored.state_store = EcosystemStateStore(tmp_path / "ecosystem-state.sqlite")
    restored.restore_learning_state()

    summary = restored.learning_summary()
    assert [item["resource_id"] for item in summary["resources"]] == ["resource-1"]
    assert summary["observations"][0]["validated"] is False
    assert summary["activities"][0]["activity_id"] == "activity-1"
    assert summary["attempts"][0]["activity_id"] == "activity-1"
    assert summary["learning_sources"][0]["status"] == "QUARANTINED"
    assert summary["learning_sources"][0]["operation_eligible"] is False
    assert summary["execution_allowed"] is False
    assert summary["learning_authorizes_trading"] is False



def test_learning_validation_rejects_truthy_non_boolean_values(tmp_path):
    store = EcosystemStateStore(tmp_path / "ecosystem-state.sqlite")
    service = EcosystemService()
    service.state_store = store
    service.add_learning_resource({
        "resource_id": "resource-2",
        "title": "Material de estudo",
        "content_type": "ARTICLE",
    })
    import pytest

    with pytest.raises(ValueError):
        service.add_learning_observation({
            "resource_id": "resource-2",
            "statement": "Não deve ser validado por string.",
            "validated": "false",
        })
    service.add_learning_activity({
        "activity_id": "activity-2",
        "prompt": "Atividade para teste de validação.",
    })
    with pytest.raises(ValueError):
        service.add_learning_attempt({
            "activity_id": "activity-2",
            "answer": "resposta",
            "correct": "true",
        })


def test_corrupt_learning_snapshot_with_string_boolean_is_discarded(tmp_path):
    store = EcosystemStateStore(tmp_path / "ecosystem-state.sqlite")
    store.save_learning({
        "sources": [{
            "source_id": "source-1",
            "source_type": "LINK",
            "uri": "https://example.com",
            "status": "VALIDATED",
            "content_verified": "false",
            "security_checked": True,
            "knowledge_validated": True,
        }],
        "resources": [],
        "observations": [],
        "activities": [],
        "attempts": [],
    })
    service = EcosystemService()
    service.state_store = store
    service.restore_learning_state()
    assert service.learning_sources == {}
    assert service.learning_resources == {}
    assert service.learning_observations == []



def test_professor_ignores_client_claim_and_requires_server_validated_knowledge(tmp_path):
    store = EcosystemStateStore(tmp_path / "ecosystem-state.sqlite")
    service = EcosystemService()
    service.state_store = store

    import pytest

    with pytest.raises(ValueError):
        service.generate_professor_activity({
            "activity_id": "untrusted-activity",
            "knowledge_id": "not-in-server-registry",
            "statement": "Afirmação enviada pelo navegador.",
            "concept": "contexto",
            "knowledge_validated": True,
        })

    source = service.screen_learning_source({
        "source_id": "verified-knowledge",
        "source_type": "LINK",
        "uri": "https://example.com/verified",
    })
    source = service.validate_learning_source(
        source, content_verified=True, security_checked=True
    )
    source = service.admit_learning_knowledge(
        source, knowledge_validated=True
    )
    assert source.knowledge_validated is True

    activity = service.generate_professor_activity({
        "activity_id": "trusted-activity",
        "knowledge_id": "verified-knowledge",
        "statement": "Afirmação revisada manualmente.",
        "concept": "contexto",
        "knowledge_validated": False,
    })
    assert activity.activity_id == "trusted-activity"
    assert "verified-knowledge" in activity.expected_concepts
