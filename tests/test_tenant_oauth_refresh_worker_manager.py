from security.tenant_context import TenantContext
from integration.tenant_oauth_refresh_worker_manager import TenantOAuthRefreshWorkerManager


class Vault:
    def refresh_candidates(self, owner, *, within_seconds, limit):
        return []


class OAuth:
    def refresh(self, owner, *, connection_id):
        raise AssertionError("no candidate should be refreshed")


def test_manager_registers_each_trusted_owner_once_and_stops_all():
    manager = TenantOAuthRefreshWorkerManager(
        Vault(), OAuth(), poll_interval_seconds=60
    )
    first = TenantContext("tenant-a", "alice")
    second = TenantContext("tenant-b", "bob")
    try:
        assert manager.register_owner(first) is True
        assert manager.register_owner(first) is False
        assert manager.register_owner(second) is True
        status = manager.status()
        assert status["registered_owner_count"] == 2
        assert status["running_owner_count"] == 2
        assert manager.running is True
    finally:
        manager.stop()
    assert manager.running is False
    assert manager.status()["registered_owner_count"] == 0


def test_manager_rejects_untrusted_owner_and_enforces_capacity():
    import pytest

    manager = TenantOAuthRefreshWorkerManager(
        Vault(), OAuth(), max_owners=1, poll_interval_seconds=60
    )
    try:
        with pytest.raises(ValueError):
            manager.register_owner(None)
        manager.register_owner(TenantContext("tenant-a", "alice"))
        with pytest.raises(RuntimeError, match="capacity"):
            manager.register_owner(TenantContext("tenant-b", "bob"))
    finally:
        manager.stop()
