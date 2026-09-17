from __future__ import annotations

from datetime import datetime, timezone

from core.ecosystem_incidents import EcosystemIncidentManager, IncidentStatus


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
