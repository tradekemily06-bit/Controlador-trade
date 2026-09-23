from __future__ import annotations

from analysis.decision_store import DecisionStore
from integration.ecosystem_service import EcosystemService


def test_learning_memory_persists_across_service_restart(tmp_path, monkeypatch):
    database = tmp_path / "learning.sqlite3"
    monkeypatch.setenv("CONTROLADOR_LEARNING_DB", str(database))

    first = EcosystemService()
    first.add_learning_resource(
        {
            "resource_id": "video-1",
            "title": "Aula de contexto",
            "content_type": "VIDEO",
            "source_url": "https://example.com/video",
            "tags": ["contexto", "M5"],
        }
    )
    first.add_learning_observation(
        {
            "resource_id": "video-1",
            "statement": "Uma confirmação deve ser analisada no contexto.",
            "concepts": ["confirmação", "contexto"],
            "validated": False,
        }
    )
    first.add_learning_activity(
        {
            "activity_id": "activity-1",
            "prompt": "Explique quais evidências sustentam a leitura.",
            "expected_concepts": ["evidência"],
            "difficulty": "INTERMEDIATE",
        }
    )
    first.add_learning_attempt(
        {
            "activity_id": "activity-1",
            "answer": "Eu verificaria evidências a favor e contra.",
            "correct": True,
            "feedback": "Boa estrutura.",
        }
    )

    second = EcosystemService()

    assert "video-1" in second.learning_resources
    assert len(second.learning_observations) == 1
    assert "activity-1" in second.learning_activities
    assert len(second.learning_attempts) == 1
    assert second.learning_sources["video-1"].operation_eligible is False
    assert second.learning_store.health == "HEALTHY"


def test_learning_persistence_is_never_reported_as_trading_authority(tmp_path, monkeypatch):
    database = tmp_path / "learning.sqlite3"
    monkeypatch.setenv("CONTROLADOR_LEARNING_DB", str(database))

    service = EcosystemService()
    summary = service.learning_summary()

    assert summary["execution_allowed"] is False
    assert summary["learning_authorizes_trading"] is False
    assert summary["learning_persistence"] == "SQLITE"
