from datetime import datetime, timedelta, timezone

from integration.tenant_oauth_refresh_worker import TenantOAuthRefreshWorker
from security.tenant_context import TenantContext


class Vault:
    def __init__(self, candidates):
        self.candidates = candidates

    def refresh_candidates(self, owner, *, within_seconds, limit):
        assert owner == TenantContext("tenant-a", "alice")
        assert within_seconds == 900
        return self.candidates[:limit]


class OAuth:
    def __init__(self, failures=()):
        self.calls = []
        self.failures = set(failures)

    def refresh(self, owner, *, connection_id):
        self.calls.append((owner, connection_id))
        if connection_id in self.failures:
            raise RuntimeError("sensitive provider response must not leak")


def test_worker_refreshes_only_candidates_and_reports_counts():
    owner = TenantContext("tenant-a", "alice")
    candidates = [
        {"connection_id": "one", "provider_id": "ctrader_open_api"},
        {"connection_id": "two", "provider_id": "ctrader_open_api"},
    ]
    vault, oauth = Vault(candidates), OAuth(failures={"two"})
    worker = TenantOAuthRefreshWorker(vault, oauth, owner)

    result = worker.run_once()

    assert result == {"candidates": 2, "refreshed": 1, "failed": 1}
    assert [item[1] for item in oauth.calls] == ["one", "two"]
    status = worker.status()
    assert status["last_scan_at"]
    assert status["last_error"] == "one_or_more_refreshes_failed"
    assert "sensitive" not in str(status)


def test_worker_empty_scan_does_not_call_provider():
    owner = TenantContext("tenant-a", "alice")
    oauth = OAuth()
    worker = TenantOAuthRefreshWorker(Vault([]), oauth, owner)

    assert worker.run_once() == {"candidates": 0, "refreshed": 0, "failed": 0}
    assert oauth.calls == []
    assert worker.status()["last_error"] is None


def test_worker_rejects_untrusted_owner_and_unsafe_intervals():
    import pytest

    with pytest.raises(ValueError):
        TenantOAuthRefreshWorker(Vault([]), OAuth(), None)
    with pytest.raises(ValueError):
        TenantOAuthRefreshWorker(Vault([]), OAuth(), TenantContext("tenant-a", "alice"),
                                 poll_interval_seconds=1)
