from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from integration.standalone_foundation_status import standalone_storage_status


class StandaloneFoundationStatusTests(unittest.TestCase):
    def test_reports_required_sqlite_stores_as_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schemas = {
                "fiscal-reserve.sqlite3": {
                    "fiscal_reserve_entries": "entry_id TEXT, owner_id TEXT, category TEXT, realized_result_brl REAL, reserve_amount_brl REAL, reference TEXT, occurred_on TEXT",
                    "fiscal_reserve_settings": "owner_id TEXT, category TEXT, rate REAL, rate_source TEXT",
                },
                "ecosystem-state.sqlite3": {"ecosystem_state": "key TEXT, value_json TEXT"},
                "notification-outbox.sqlite3": {"notification_outbox": "idempotency_key TEXT, payload_json TEXT, status TEXT, attempts INTEGER, available_at REAL, created_at REAL"},
                "decision-memory.sqlite3": {"decisions": "decision_id TEXT, created_at TEXT, signal TEXT, score REAL, confirmed INTEGER, reason TEXT, execution_allowed INTEGER, outcome_source TEXT"},
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
        self.assertFalse(result["execution_authorized"])

    def test_missing_required_store_degrades_foundation_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in (
                "fiscal-reserve.sqlite3",
                "ecosystem-state.sqlite3",
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
                    "fiscal_reserve_entries": "entry_id TEXT, owner_id TEXT, category TEXT, realized_result_brl REAL, reserve_amount_brl REAL, reference TEXT, occurred_on TEXT",
                    "fiscal_reserve_settings": "owner_id TEXT, category TEXT, rate REAL, rate_source TEXT",
                },
                "ecosystem-state.sqlite3": {"ecosystem_state": "key TEXT, value_json TEXT"},
                "notification-outbox.sqlite3": {"notification_outbox": "idempotency_key TEXT, payload_json TEXT, status TEXT, attempts INTEGER, available_at REAL, created_at REAL"},
                "decision-memory.sqlite3": {"decisions": "decision_id TEXT, created_at TEXT, signal TEXT, score REAL, confirmed INTEGER, reason TEXT, execution_allowed INTEGER"},
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
                "fiscal-reserve.sqlite3": ("fiscal_reserve_entries", "fiscal_reserve_settings"),
                "ecosystem-state.sqlite3": ("ecosystem_state",),
                "notification-outbox.sqlite3": ("notification_outbox",),
                "assistant-conversations.sqlite3": ("conversations", "messages"),
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


if __name__ == "__main__":
    unittest.main()
