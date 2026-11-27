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
