from pathlib import Path

from core.ecosystem_incidents import EcosystemIncidentManager, IncidentStatus
from core.ecosystem_notifications import EcosystemNotificationCenter, NotificationSeverity
from core.technical_incident_store import TechnicalIncidentStore


def test_unexpected_incident_blocks_execution_and_notifies_user():
    center = EcosystemNotificationCenter()
    incidents = EcosystemIncidentManager(notification_center=center)

    incident = incidents.open_incident(
        incident_id="incident-test-1",
        title="Problema técnico",
        message="Um componente crítico apresentou uma falha inesperada.",
    )

    assert incident.status is IncidentStatus.ACTIVE
    assert incidents.execution_blocked() is True
    visible = center.visible()
    assert len(visible) == 1
    assert visible[0].severity is NotificationSeverity.CRITICAL
    assert visible[0].blocking is True
    assert "Novas ordens estão bloqueadas" in visible[0].message


def test_incident_requires_explicit_resolution_before_unblocking():
    incidents = EcosystemIncidentManager()
    incident = incidents.open_incident(
        incident_id="incident-test-2",
        title="Falha",
        message="Serviço indisponível.",
    )
    assert incidents.execution_blocked() is True

    resolved = incidents.resolve_incident(incident.incident_id)
    assert resolved.status is IncidentStatus.RESOLVED
    assert incidents.execution_blocked() is False


def test_persistent_incident_blocks_after_manager_restart_and_only_resolution_unblocks(tmp_path: Path):
    store_path = tmp_path / "technical-incident.json"
    first = EcosystemIncidentManager(store=TechnicalIncidentStore(store_path))
    incident = first.open_incident(
        incident_id="incident-persistent-1",
        title="Falha persistente",
        message="Estado crítico persistido para recuperação.",
    )

    restarted = EcosystemIncidentManager(store=TechnicalIncidentStore(store_path))
    active = restarted.active()

    assert incident.status is IncidentStatus.ACTIVE
    assert restarted.execution_blocked() is True
    assert restarted.status()["execution_blocked"] is True
    assert tuple(item.incident_id for item in active) == ("incident-persistent-1",)

    resolved = restarted.resolve_incident("incident-persistent-1")

    assert resolved.status is IncidentStatus.RESOLVED
    assert restarted.execution_blocked() is False
    assert restarted.status()["status"] == "HEALTHY"


def test_corrupt_persistent_incident_state_fails_closed(tmp_path: Path):
    store_path = tmp_path / "technical-incident.json"
    store_path.write_text("{corrupted", encoding="utf-8")
    incidents = EcosystemIncidentManager(store=TechnicalIncidentStore(store_path))

    assert incidents.execution_blocked() is True
    active = incidents.active()
    assert len(active) == 1
    assert active[0].incident_id == "incident-state-unavailable"
    assert active[0].execution_blocked is True

    status = incidents.status()
    assert status["status"] == "INCIDENT"
    assert status["execution_blocked"] is True
    assert status["active_incidents"] == ("incident-state-unavailable",)
    assert "permanece bloqueada" in status["reason"]
