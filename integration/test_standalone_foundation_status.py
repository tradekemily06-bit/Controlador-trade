from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from integration.standalone_foundation_status import standalone_storage_status


def _create_table(path, ddl):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(ddl)


def test_missing_tenant_market_data_database_degrades_storage_readiness(tmp_path):
    status = standalone_storage_status(SimpleNamespace(runtime_dir=tmp_path))

    tenant_store = next(item for item in status["stores"] if item["id"] == "tenant_market_data")
    assert tenant_store["required"] is True
    assert tenant_store["state"] == "MISSING"
    assert status["required_stores"] == "DEGRADED"


def test_notification_outbox_readiness_requires_lease_fencing_column(tmp_path):
    path = tmp_path / "notification-outbox.sqlite3"
    _create_table(
        path,
        """
        CREATE TABLE notification_outbox (
            idempotency_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            available_at REAL NOT NULL,
            lease_until REAL,
            created_at REAL NOT NULL,
            delivered_at REAL,
            last_error TEXT
        )
        """,
    )

    status = standalone_storage_status(SimpleNamespace(runtime_dir=tmp_path))
    outbox = next(item for item in status["stores"] if item["id"] == "notification_outbox")

    assert outbox["state"] == "SCHEMA_INCOMPLETE"
    assert outbox["missing_schema"]["notification_outbox"] == ["lease_token"]
    assert status["required_stores"] == "DEGRADED"



def test_news_and_calendar_stores_are_visible_but_optional_in_readiness(tmp_path):
    status = standalone_storage_status(SimpleNamespace(runtime_dir=tmp_path))

    news = next(item for item in status["stores"] if item["id"] == "news_evidence")
    calendar = next(item for item in status["stores"] if item["id"] == "economic_calendar")

    assert news["required"] is False
    assert news["state"] == "MISSING"
    assert calendar["required"] is False
    assert calendar["state"] == "MISSING"



def test_signal_evidence_store_is_visible_but_optional_in_readiness(tmp_path):
    status = standalone_storage_status(SimpleNamespace(runtime_dir=tmp_path))

    evidence = next(
        item for item in status["stores"] if item["id"] == "tenant_signal_evidence"
    )

    assert evidence["required"] is False
    assert evidence["state"] == "MISSING"



def test_forecast_and_security_audit_stores_are_optional_readiness_entries(tmp_path):
    status = standalone_storage_status(SimpleNamespace(runtime_dir=tmp_path))

    forecast = next(item for item in status["stores"] if item["id"] == "tenant_forecast_audit")
    security = next(item for item in status["stores"] if item["id"] == "security_audit")

    assert forecast["required"] is False
    assert forecast["state"] == "MISSING"
    assert security["required"] is False
    assert security["state"] == "MISSING"



def test_forecast_and_security_audit_schema_are_checked_when_present(tmp_path):
    from analysis.tenant_forecast_audit_store import TenantForecastAuditStore
    from security_audit import SecurityAudit

    TenantForecastAuditStore(tmp_path / "tenant-forecast-audit.sqlite3")
    SecurityAudit(database_path=str(tmp_path / "security-audit.sqlite3"))

    status = standalone_storage_status(SimpleNamespace(runtime_dir=tmp_path))
    forecast = next(item for item in status["stores"] if item["id"] == "tenant_forecast_audit")
    security = next(item for item in status["stores"] if item["id"] == "security_audit")

    assert forecast["state"] == "HEALTHY"
    assert security["state"] == "HEALTHY"
