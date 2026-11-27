from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from integration.standalone_foundation_status import _integrity, standalone_storage_status


class StandaloneFoundationStatusTests(unittest.TestCase):
    def test_missing_runtime_directory_reports_production_blockers(self):
        result = standalone_storage_status(SimpleNamespace(runtime_dir=None))

        self.assertEqual(result["required_stores"], "NOT_AVAILABLE")
        self.assertEqual(result["deployment_topology"], "UNKNOWN_NO_RUNTIME_DIRECTORY")
        self.assertEqual(result["multi_replica_readiness"], "BLOCKED_RUNTIME_NOT_AVAILABLE")
        self.assertIn("RUNTIME_STORAGE_NOT_AVAILABLE", result["production_release_blockers"])
        self.assertIn("EXTERNAL_NOTIFICATION_DELIVERY_PROVIDER", result["production_release_blockers"])
        self.assertIn("TRUSTED_IDENTITY_PROVIDER_RUNTIME_VERIFICATION", result["production_release_blockers"])
        self.assertFalse(result["execution_authorized"])

    def test_reports_required_sqlite_stores_as_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schemas = {
                "fiscal-reserve.sqlite3": {
                    "fiscal_reserve_entries": "entry_id TEXT, owner_id TEXT, category TEXT, entry_type TEXT, realized_result_brl REAL, reserve_rate REAL, reserve_amount_brl REAL, reference TEXT, occurred_on TEXT, created_at TEXT, notes TEXT",
                    "fiscal_reserve_settings": "owner_id TEXT, category TEXT, rate REAL, rate_source TEXT",
                    "fiscal_reserve_pending_foreign": "pending_id TEXT, owner_id TEXT, reference TEXT, original_amount REAL, original_currency TEXT, instrument TEXT, jurisdiction TEXT, occurred_on TEXT, status TEXT, created_at TEXT",
                    "fiscal_pending_reviews": "review_id TEXT, owner_id TEXT, pending_id TEXT, candidate_classification TEXT, confirmed_jurisdiction TEXT, reviewer_name TEXT, reviewer_role TEXT, professional_registration TEXT, evidence_reference TEXT, reviewed_on TEXT, created_at TEXT",
                    "fiscal_reserve_pending_domestic": "pending_id TEXT, owner_id TEXT, reference TEXT, instrument TEXT, occurred_on TEXT, status TEXT, created_at TEXT",
                    "fiscal_domestic_pending_reviews": "review_id TEXT, owner_id TEXT, pending_id TEXT, candidate_classification TEXT, confirmed_jurisdiction TEXT, reviewer_name TEXT, reviewer_role TEXT, professional_registration TEXT, evidence_reference TEXT, reviewed_on TEXT, created_at TEXT",
                },
                "ecosystem-state.sqlite3": {"ecosystem_state": "key TEXT, value_json TEXT"},
                "tenant-state.sqlite3": {"tenant_state": "tenant_id TEXT, subject_id TEXT, key TEXT, value_json TEXT, updated_at TEXT"},
                "tenant-connection-timeframe-monitor.sqlite3": {
                    "tenant_connection_timeframe_watch": "tenant_id TEXT, subject_id TEXT, connection_id TEXT, symbol TEXT, timeframe TEXT, enabled INTEGER, created_at REAL, last_processed_candle TEXT, last_signal TEXT, last_status TEXT, last_error TEXT",
                    "tenant_connection_timeframe_results": "tenant_id TEXT, subject_id TEXT, connection_id TEXT, symbol TEXT, timeframe TEXT, candle_at TEXT, result_json TEXT, recorded_at REAL",
                    "tenant_connection_timeframe_processing_lease": "lease_key TEXT, owner_token TEXT, expires_at REAL",
                    "tenant_connection_notification_outbox": "event_id TEXT, tenant_id TEXT, subject_id TEXT, connection_id TEXT, symbol TEXT, timeframe TEXT, candle_at TEXT, result_json TEXT, created_at REAL, attempts INTEGER, lease_until REAL, lease_token TEXT, delivered_at REAL, dead_at REAL, last_error TEXT",
                },
                "tenant-mt5-relay-tokens.sqlite3": {
                    "tenant_mt5_relay_tokens": "token_hash TEXT, tenant_id TEXT, subject_id TEXT, connection_id TEXT, source_id TEXT, created_at REAL, revoked INTEGER",
                },
                "tenant-tradingview-webhook-secrets.sqlite3": {
                    "tenant_tradingview_webhook_secrets": "secret_hash TEXT, tenant_id TEXT, subject_id TEXT, connection_id TEXT, revoked INTEGER",
                },
                "notification-outbox.sqlite3": {"notification_outbox": "idempotency_key TEXT, payload_json TEXT, status TEXT, attempts INTEGER, available_at REAL, lease_until REAL, lease_token TEXT, created_at REAL, delivered_at REAL, last_error TEXT"},
                "decision-memory.sqlite3": {"decisions": "decision_id TEXT, created_at TEXT, symbol TEXT, timeframe TEXT, signal TEXT, score REAL, confirmed INTEGER, reason TEXT, execution_allowed INTEGER, outcome TEXT, outcome_source TEXT"},
                "assistant-conversations.sqlite3": {
                    "conversations": "id TEXT, owner TEXT, title TEXT, updated_at TEXT",
                    "messages": "id INTEGER, conversation_id TEXT, role TEXT, content TEXT, created_at TEXT",
                },
            }
            for filename, tables in schemas.items():
                with sqlite3.connect(root / filename) as connection:
                    for table, columns in tables.items():
                        connection.execute(f"CREATE TABLE {table} ({columns})")
            result = standalone_storage_status(SimpleNamespace(runtime_dir=root))
        self.assertEqual(result["required_stores"], "HEALTHY")
        self.assertEqual(result["multi_tenant_isolation"], "NOT_IMPLEMENTED")
        self.assertEqual(result["backup_restore"], "NOT_CONFIGURED")
        self.assertEqual(result["deployment_topology"], "SINGLE_HOST_ONLY")
        self.assertEqual(
            result["multi_replica_readiness"],
            "BLOCKED_SHARED_TRANSACTIONAL_DATABASE_REQUIRED",
        )
        self.assertIn(
            "DURABLE_SHARED_OAUTH_STORAGE_WITH_KMS",
            result["production_release_blockers"],
        )
        self.assertIn("EXTERNAL_NOTIFICATION_DELIVERY_PROVIDER", result["production_release_blockers"])
        self.assertIn("TRUSTED_IDENTITY_PROVIDER_RUNTIME_VERIFICATION", result["production_release_blockers"])
        self.assertFalse(result["execution_authorized"])

    def test_missing_fiscal_pending_queue_degrades_fiscal_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with sqlite3.connect(root / "fiscal-reserve.sqlite3") as connection:
                connection.execute("""
                    CREATE TABLE fiscal_reserve_entries (
                        entry_id TEXT, owner_id TEXT, category TEXT, entry_type TEXT,
                        realized_result_brl REAL, reserve_rate REAL, reserve_amount_brl REAL,
                        reference TEXT, occurred_on TEXT, created_at TEXT, notes TEXT
                    )
                """)
                connection.execute("""
                    CREATE TABLE fiscal_reserve_settings (
                        owner_id TEXT, category TEXT, rate REAL, rate_source TEXT
                    )
                """)
            result = standalone_storage_status(SimpleNamespace(runtime_dir=root))
        fiscal = next(item for item in result["stores"] if item["id"] == "fiscal")
        self.assertEqual(fiscal["state"], "SCHEMA_INCOMPLETE")
        self.assertEqual(fiscal["missing_schema"]["fiscal_reserve_pending_foreign"], ["<table>"])
        self.assertEqual(result["required_stores"], "DEGRADED")

    def test_tenant_scoped_market_monitor_schema_is_recognized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with sqlite3.connect(root / "market-timeframe-monitor.sqlite3") as connection:
                connection.execute("""
                    CREATE TABLE market_timeframe_watch_v2 (
                        tenant_id TEXT, subject_id TEXT, symbol TEXT, timeframe TEXT,
                        enabled INTEGER, created_at REAL, last_processed_candle TEXT,
                        last_signal TEXT, last_status TEXT, last_error TEXT
                    )
                """)
                connection.execute("""
                    CREATE TABLE market_timeframe_results_v2 (
                        tenant_id TEXT, subject_id TEXT, symbol TEXT, timeframe TEXT,
                        candle_at TEXT, result_json TEXT, recorded_at REAL
                    )
                """)
            result = standalone_storage_status(SimpleNamespace(runtime_dir=root))
        monitor = next(item for item in result["stores"] if item["id"] == "market_timeframe_monitor")
        self.assertEqual(monitor["state"], "HEALTHY")
        self.assertFalse(monitor["required"])

    def test_missing_required_store_degrades_foundation_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in (
                "fiscal-reserve.sqlite3",
                "ecosystem-state.sqlite3",
                "tenant-state.sqlite3",
                "notification-outbox.sqlite3",
                "decision-memory.sqlite3",
            ):
                with sqlite3.connect(root / filename) as connection:
                    connection.execute("CREATE TABLE foundation_probe (id INTEGER)")
            result = standalone_storage_status(SimpleNamespace(runtime_dir=root))
        self.assertEqual(result["required_stores"], "DEGRADED")
        assistant = next(item for item in result["stores"] if item["id"] == "assistant_conversations")
        self.assertEqual(assistant["state"], "MISSING")
        self.assertTrue(assistant["required"])

    def test_empty_but_valid_sqlite_is_schema_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in (
                "fiscal-reserve.sqlite3",
                "ecosystem-state.sqlite3",
                "tenant-state.sqlite3",
                "notification-outbox.sqlite3",
                "decision-memory.sqlite3",
                "assistant-conversations.sqlite3",
            ):
                sqlite3.connect(root / filename).close()
            result = standalone_storage_status(SimpleNamespace(runtime_dir=root))
        self.assertEqual(result["required_stores"], "DEGRADED")
        decision = next(item for item in result["stores"] if item["id"] == "decision_memory")
        self.assertEqual(decision["state"], "SCHEMA_INCOMPLETE")
        self.assertEqual(decision["missing_schema"], {"decisions": ["<table>"]})

    def test_missing_required_column_degrades_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schemas = {
                "fiscal-reserve.sqlite3": {
                    "fiscal_reserve_entries": "entry_id TEXT, owner_id TEXT, category TEXT, entry_type TEXT, realized_result_brl REAL, reserve_rate REAL, reserve_amount_brl REAL, reference TEXT, occurred_on TEXT, created_at TEXT, notes TEXT",
                    "fiscal_reserve_settings": "owner_id TEXT, category TEXT, rate REAL, rate_source TEXT",
                    "fiscal_reserve_pending_foreign": "pending_id TEXT, owner_id TEXT, reference TEXT, original_amount REAL, original_currency TEXT, instrument TEXT, jurisdiction TEXT, occurred_on TEXT, status TEXT, created_at TEXT",
                    "fiscal_pending_reviews": "review_id TEXT, owner_id TEXT, pending_id TEXT, candidate_classification TEXT, confirmed_jurisdiction TEXT, reviewer_name TEXT, reviewer_role TEXT, professional_registration TEXT, evidence_reference TEXT, reviewed_on TEXT, created_at TEXT",
                    "fiscal_reserve_pending_domestic": "pending_id TEXT, owner_id TEXT, reference TEXT, instrument TEXT, occurred_on TEXT, status TEXT, created_at TEXT",
                    "fiscal_domestic_pending_reviews": "review_id TEXT, owner_id TEXT, pending_id TEXT, candidate_classification TEXT, confirmed_jurisdiction TEXT, reviewer_name TEXT, reviewer_role TEXT, professional_registration TEXT, evidence_reference TEXT, reviewed_on TEXT, created_at TEXT",
                },
                "ecosystem-state.sqlite3": {"ecosystem_state": "key TEXT, value_json TEXT"},
                "tenant-state.sqlite3": {"tenant_state": "tenant_id TEXT, subject_id TEXT, key TEXT, value_json TEXT, updated_at TEXT"},
                "notification-outbox.sqlite3": {"notification_outbox": "idempotency_key TEXT, payload_json TEXT, status TEXT, attempts INTEGER, available_at REAL, lease_until REAL, created_at REAL, delivered_at REAL, last_error TEXT"},
                "decision-memory.sqlite3": {"decisions": "decision_id TEXT, created_at TEXT, symbol TEXT, timeframe TEXT, signal TEXT, score REAL, confirmed INTEGER, reason TEXT, execution_allowed INTEGER, outcome TEXT"},
                "assistant-conversations.sqlite3": {
                    "conversations": "id TEXT, owner TEXT, title TEXT, updated_at TEXT",
                    "messages": "id INTEGER, conversation_id TEXT, role TEXT, content TEXT, created_at TEXT",
                },
            }
            for filename, tables in schemas.items():
                with sqlite3.connect(root / filename) as connection:
                    for table, columns in tables.items():
                        connection.execute(f"CREATE TABLE {table} ({columns})")
            result = standalone_storage_status(SimpleNamespace(runtime_dir=root))
        self.assertEqual(result["required_stores"], "DEGRADED")
        decision = next(item for item in result["stores"] if item["id"] == "decision_memory")
        self.assertEqual(decision["state"], "SCHEMA_INCOMPLETE")
        self.assertEqual(decision["missing_schema"], {"decisions": ["outcome_source"]})

    def test_corrupt_required_store_is_not_reported_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schemas = {
                "fiscal-reserve.sqlite3": {
                    "fiscal_reserve_entries": "entry_id TEXT, owner_id TEXT, category TEXT, realized_result_brl REAL, reserve_amount_brl REAL, reference TEXT, occurred_on TEXT",
                    "fiscal_reserve_settings": "owner_id TEXT, category TEXT, rate REAL, rate_source TEXT",
                    "fiscal_reserve_pending_foreign": "pending_id TEXT, owner_id TEXT, reference TEXT, original_amount REAL, original_currency TEXT, instrument TEXT, jurisdiction TEXT, occurred_on TEXT, status TEXT, created_at TEXT",
                    "fiscal_pending_reviews": "review_id TEXT, owner_id TEXT, pending_id TEXT, candidate_classification TEXT, confirmed_jurisdiction TEXT, reviewer_name TEXT, reviewer_role TEXT, professional_registration TEXT, evidence_reference TEXT, reviewed_on TEXT, created_at TEXT",
                    "fiscal_reserve_pending_domestic": "pending_id TEXT, owner_id TEXT, reference TEXT, instrument TEXT, occurred_on TEXT, status TEXT, created_at TEXT",
                    "fiscal_domestic_pending_reviews": "review_id TEXT, owner_id TEXT, pending_id TEXT, candidate_classification TEXT, confirmed_jurisdiction TEXT, reviewer_name TEXT, reviewer_role TEXT, professional_registration TEXT, evidence_reference TEXT, reviewed_on TEXT, created_at TEXT",
                },
                "ecosystem-state.sqlite3": {"ecosystem_state": "key TEXT, value_json TEXT"},
                "tenant-state.sqlite3": {"tenant_state": "tenant_id TEXT, subject_id TEXT, key TEXT, value_json TEXT, updated_at TEXT"},
                "notification-outbox.sqlite3": {"notification_outbox": "idempotency_key TEXT, payload_json TEXT, status TEXT, attempts INTEGER, available_at REAL, created_at REAL"},
                "assistant-conversations.sqlite3": {
                    "conversations": "id TEXT, owner TEXT, title TEXT, updated_at TEXT",
                    "messages": "id INTEGER, conversation_id TEXT, role TEXT, content TEXT, created_at TEXT",
                },
            }
            for filename, tables in schemas.items():
                with sqlite3.connect(root / filename) as connection:
                    for table, columns in tables.items():
                        connection.execute(f"CREATE TABLE {table} ({columns})")
            (root / "decision-memory.sqlite3").write_bytes(b"not a sqlite database")
            result = standalone_storage_status(SimpleNamespace(runtime_dir=root))
        self.assertEqual(result["required_stores"], "DEGRADED")
        decision = next(item for item in result["stores"] if item["id"] == "decision_memory")
        self.assertEqual(decision["state"], "UNREADABLE")

    def test_foreign_key_violation_is_reported_as_integrity_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute("PRAGMA foreign_keys = OFF")
                connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
                connection.execute(
                    "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"
                )
                connection.execute("INSERT INTO child (parent_id) VALUES (404)")
            integrity, missing = _integrity(path, {"child": {"parent_id"}})
        self.assertEqual(integrity, "FOREIGN_KEY_VIOLATIONS:1")
        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()
