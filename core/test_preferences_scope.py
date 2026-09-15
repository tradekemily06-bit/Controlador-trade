from __future__ import annotations

import pytest

from core.ecosystem_preferences import EcosystemPreferencesStore
from security.http_identity import clear_trusted_identity, require_trusted_identity


class MemoryStateStore:
    def __init__(self):
        self.values = {}

    def get(self, *, tenant_id, subject_id, namespace):
        return self.values.get((tenant_id, subject_id, namespace))

    def put(self, *, tenant_id, subject_id, namespace, payload):
        self.values[(tenant_id, subject_id, namespace)] = payload


def _identity(tenant_id: str, subject_id: str) -> None:
    require_trusted_identity(
        {
            "PATH_INFO": "/api/test",
            "controlador.trusted_tenant_id": tenant_id,
            "controlador.trusted_subject_id": subject_id,
            "controlador.trusted_role": "user",
        }
    )


def test_durable_preferences_fail_closed_without_trusted_scope() -> None:
    store = EcosystemPreferencesStore(state_store=MemoryStateStore())
    clear_trusted_identity()
    with pytest.raises(PermissionError, match="trusted tenant and subject scope"):
        _ = store.preferences
    with pytest.raises(PermissionError, match="trusted tenant and subject scope"):
        store.update(default_timeframe="1m")


def test_durable_preferences_are_scoped_and_survive_service_instances() -> None:
    state = MemoryStateStore()
    first = EcosystemPreferencesStore(state_store=state)
    _identity("tenant-a", "user-a")
    try:
        first.update(default_timeframe="1m")
        assert first.preferences.default_timeframe == "1m"

        _identity("tenant-b", "user-b")
        second = EcosystemPreferencesStore(state_store=state)
        assert second.preferences.default_timeframe == "5m"

        _identity("tenant-a", "user-a")
        restarted = EcosystemPreferencesStore(state_store=state)
        assert restarted.preferences.default_timeframe == "1m"
    finally:
        clear_trusted_identity()
