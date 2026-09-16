from core.ecosystem_incidents import EcosystemIncidentManager, IncidentStatus
from core.ecosystem_notifications import EcosystemNotificationCenter, NotificationSeverity


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
