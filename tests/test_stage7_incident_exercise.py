from __future__ import annotations

from datetime import datetime, timezone

from core.ecosystem_incidents import EcosystemIncidentManager, IncidentStatus
from core.technical_incident_store import TechnicalIncidentStore


def test_incident_lifecycle_blocks_then_recovers():
    manager = EcosystemIncidentManager()
    opened = manager.open_incident(
        title="Stage 7 exercise",
        message="synthetic incident used to verify fail-closed behavior",
        incident_id="stage7-exercise",
        now=datetime(2026, 9, 17, tzinfo=timezone.utc),
    )

    assert opened.status is IncidentStatus.ACTIVE
    assert manager.execution_blocked() is True
    assert manager.status()["execution_blocked"] is True

    resolved = manager.resolve_incident(
        "stage7-exercise",
        now=datetime(2026, 9, 17, 0, 1, tzinfo=timezone.utc),
    )

    assert resolved.status is IncidentStatus.RESOLVED
    assert manager.execution_blocked() is False
    assert manager.status()["status"] == "HEALTHY"


def test_persisted_incident_survives_new_manager_instance(tmp_path):
    store = TechnicalIncidentStore(tmp_path / "incident.json")
    first = EcosystemIncidentManager(store=store)
    first.open_incident(
        title="Persistent exercise",
        message="incident must remain blocking after restart",
        incident_id="persistent-stage7",
        now=datetime(2026, 9, 17, tzinfo=timezone.utc),
    )

    second = EcosystemIncidentManager(store=store)
    assert second.execution_blocked() is True
    assert second.status()["active_incidents"] == ("persistent-stage7",)


def test_corrupt_persisted_incident_state_fails_closed(tmp_path):
    path = tmp_path / "incident.json"
    path.write_text('{"status":"INCIDENT"}', encoding="utf-8")

    manager = EcosystemIncidentManager(store=TechnicalIncidentStore(path))

    assert manager.execution_blocked() is True
    status = manager.status()
    assert status["execution_blocked"] is True
    assert status["status"] == "INCIDENT"


def test_missing_persisted_incident_file_is_healthy(tmp_path):
    manager = EcosystemIncidentManager(
        store=TechnicalIncidentStore(tmp_path / "missing-incident.json")
    )

    assert manager.execution_blocked() is False
    assert manager.status()["status"] == "HEALTHY"
