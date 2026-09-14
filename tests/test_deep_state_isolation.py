from __future__ import annotations

from analysis.decision_record import DecisionRecord
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService
from security.http_identity import TRUSTED_ROLE_KEY, TRUSTED_SUBJECT_KEY, TRUSTED_TENANT_KEY, clear_trusted_identity, require_trusted_identity


def _identity(tenant: str, subject: str):
    environ = {TRUSTED_TENANT_KEY: tenant, TRUSTED_SUBJECT_KEY: subject, TRUSTED_ROLE_KEY: "user"}
    return require_trusted_identity(environ)


def _record(service: ConfiguredEcosystemService, tenant: str, subject: str, score: float):
    _identity(tenant, subject)
    try:
        return service.analyze({"score": score, "confirmed": True, "filters_ok": True, "symbol": "EURUSD", "timeframe": "5m", "operational_state": {"trades_today": 0, "consecutive_losses": 0}})
    finally:
        clear_trusted_identity()


def test_memory_and_statistics_are_scoped_to_trusted_subject_and_tenant():
    service = ConfiguredEcosystemService()
    first = _record(service, "tenant-a", "user-a", 90)
    second = _record(service, "tenant-b", "user-b", 80)

    assert first.tenant_id == "tenant-a"
    assert second.tenant_id == "tenant-b"
    assert [item["decision_id"] for item in service.memory_view(subject_id="user-a", tenant_id="tenant-a")] == [first.decision_id]
    assert service.statistics(subject_id="user-a", tenant_id="tenant-a")["total"] == 1
    assert service.memory_view(subject_id="user-b", tenant_id="tenant-b")[0]["decision_id"] == second.decision_id
    assert service.memory_view(subject_id="user-a", tenant_id="tenant-b") == []


def test_owned_decision_cannot_be_updated_without_matching_scope():
    service = ConfiguredEcosystemService()
    record = _record(service, "tenant-a", "user-a", 90)

    try:
        _identity("tenant-b", "user-b")
        try:
            service.record_outcome(record.decision_id, "WIN")
            raise AssertionError("cross-scope update unexpectedly succeeded")
        except PermissionError:
            pass
    finally:
        clear_trusted_identity()


def test_psychology_history_does_not_collect_when_disabled():
    service = ConfiguredEcosystemService()
    service.preferences.update(psychology_data_collection_enabled=False)
    result = service.advanced_psychology_assessment({"trades_count": 10, "losses": 3, "consecutive_losses": 3, "urge_to_trade": 8})
    assert result["history"]["enabled"] is False
    assert result["history"]["reason"] == "behavioral data collection is disabled"


def test_psychology_history_uses_only_current_scope():
    service = ConfiguredEcosystemService()
    _record(service, "tenant-a", "user-a", 90)
    _record(service, "tenant-b", "user-b", 90)

    _identity("tenant-a", "user-a")
    try:
        result = service.advanced_psychology_assessment({"urge_to_trade": 0})
        assert result["history"]["trading_authorized"] is False
        assert result["history"]["risk_level"] in {"LOW", "MODERATE", "HIGH"}
    finally:
        clear_trusted_identity()
