from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.technical_incident_store import TechnicalIncidentStore


def test_active_incident_cannot_be_silently_replaced(tmp_path):
    store = TechnicalIncidentStore(tmp_path / "incident.json")
    now = datetime.now(timezone.utc)
    store.open("incident-a", "first", now=now)

    with pytest.raises(ValueError, match="outro incidente"):
        TechnicalIncidentStore(store.path).open("incident-b", "second", now=now)

    assert store.status()["incident_id"] == "incident-a"
    assert store.status()["reason"] == "first"


def test_same_incident_can_be_reasserted_without_changing_identity(tmp_path):
    store = TechnicalIncidentStore(tmp_path / "incident.json")
    now = datetime.now(timezone.utc)
    store.open("incident-a", "first", now=now)
    store.open("incident-a", "updated", now=now)

    status = store.status()
    assert status["status"] == "INCIDENT"
    assert status["incident_id"] == "incident-a"
    assert status["reason"] == "updated"
