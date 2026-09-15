from __future__ import annotations

from core.ecosystem_preferences import EcosystemPreferencesStore
from security.http_identity import clear_trusted_identity, require_trusted_identity
from storage.scoped_state_store import SQLiteScopedStateStore


def _identity(tenant: str, subject: str):
    require_trusted_identity({
        "PATH_INFO": "/api/preferences",
        "controlador.trusted_tenant_id": tenant,
        "controlador.trusted_subject_id": subject,
        "controlador.trusted_role": "user",
    })


def test_preferences_are_durable_and_isolated(tmp_path):
    state = SQLiteScopedStateStore(tmp_path / "state.db")
    try:
        _identity("tenant-a", "user-a")
        first = EcosystemPreferencesStore(state_store=state)
        first.update(default_symbol="GBPUSD")

        _identity("tenant-b", "user-a")
        assert EcosystemPreferencesStore(state_store=state).preferences.default_symbol == "EURUSD"

        _identity("tenant-a", "user-a")
        restarted = EcosystemPreferencesStore(state_store=state)
        assert restarted.preferences.default_symbol == "GBPUSD"
    finally:
        clear_trusted_identity()
