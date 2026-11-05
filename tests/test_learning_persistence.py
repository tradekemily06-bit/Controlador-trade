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
    with pytest.raises(ValueError):
        service.add_learning_attempt({
            "activity_id": "activity-missing",
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
