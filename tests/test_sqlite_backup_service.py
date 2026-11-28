from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.sqlite_backup_service import BACKUP_DATABASES, SQLiteBackupService


class SQLiteBackupServiceTests(unittest.TestCase):
    def test_creates_verified_backup_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            source = runtime / "decision-memory.sqlite3"
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE decisions (decision_id TEXT)")
                db.execute("INSERT INTO decisions VALUES ('d-1')")
            result = SQLiteBackupService(runtime, backups).backup(["decision_memory"])
            item = result["results"][0]
            self.assertEqual(item["status"], "BACKUP_CREATED")
            backup = backups / item["filename"]
            with sqlite3.connect(backup) as db:
                self.assertEqual(db.execute("SELECT decision_id FROM decisions").fetchone()[0], "d-1")
            with sqlite3.connect(source) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0], 1)
            self.assertFalse(result["restore_tested"])

    def test_restore_verification_uses_isolated_copy_and_leaves_live_db_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            source = runtime / "decision-memory.sqlite3"
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE decisions (decision_id TEXT)")
                db.execute("INSERT INTO decisions VALUES (?)", ("restore-record",))
            service = SQLiteBackupService(runtime, backups)
            created = service.backup(["decision_memory"])["results"][0]
            result = service.verify_restore("decision_memory", created["filename"])
            self.assertEqual(result["status"], "RESTORE_VALIDATED_IN_ISOLATION")
            self.assertFalse(result["live_database_modified"])
            with sqlite3.connect(source) as db:
                self.assertEqual(db.execute("SELECT decision_id FROM decisions").fetchone()[0], "restore-record")
            self.assertFalse(list(backups.glob(".decision_memory-restore-test-*")))

    def test_restore_verification_checks_rows_in_the_isolated_restored_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            source = runtime / "decision-memory.sqlite3"
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE decisions (decision_id TEXT)")
                db.execute("INSERT INTO decisions VALUES (?)", ("durable-decision",))

            service = SQLiteBackupService(runtime, backups)
            created = service.backup(["decision_memory"])["results"][0]
            original_check = SQLiteBackupService._check
            inspected_rows = []

            def inspect_restored_copy(path):
                original_check(path)
                with sqlite3.connect(path) as restored:
                    inspected_rows.append(
                        restored.execute(
                            "SELECT decision_id FROM decisions"
                        ).fetchone()[0]
                    )

            with patch.object(
                SQLiteBackupService, "_check", side_effect=inspect_restored_copy
            ):
                result = service.verify_restore("decision_memory", created["filename"])

            self.assertEqual(result["status"], "RESTORE_VALIDATED_IN_ISOLATION")
            self.assertEqual(inspected_rows, ["durable-decision"])
            with sqlite3.connect(source) as db:
                self.assertEqual(
                    db.execute("SELECT decision_id FROM decisions").fetchone()[0],
                    "durable-decision",
                )
            self.assertFalse(list(backups.glob(".decision_memory-restore-test-*")))

    def test_restore_verification_rejects_traversal_and_wrong_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = SQLiteBackupService(root / "runtime", root / "backups")
            with self.assertRaisesRegex(ValueError, "invalid backup filename"):
                service.verify_restore("decision_memory", "../decision_memory-20261127T010203000000Z.sqlite3")
            with self.assertRaisesRegex(ValueError, "does not match"):
                service.verify_restore("decision_memory", "fiscal-20261127T010203000000Z.sqlite3")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                service.verify_restore("arbitrary_path", "arbitrary_path-20261127T010203000000Z.sqlite3")

    def test_publish_never_overwrites_existing_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            temporary = root / "temporary.sqlite3"
            destination = root / "existing.sqlite3"
            temporary.write_bytes(b"new backup")
            destination.write_bytes(b"keep existing")
            with self.assertRaises(FileExistsError):
                SQLiteBackupService._publish_exclusive(temporary, destination)
            self.assertEqual(destination.read_bytes(), b"keep existing")
            self.assertTrue(temporary.exists())

    def test_tenant_state_database_is_included_in_allowlisted_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            source = runtime / "tenant-state.sqlite3"
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE tenant_state (tenant_id TEXT, subject_id TEXT, key TEXT)")
                db.execute("INSERT INTO tenant_state VALUES (?, ?, ?)", ("tenant-a", "user-a", "prefs"))
            result = SQLiteBackupService(runtime, backups).backup(["tenant_state"])
            item = result["results"][0]
            self.assertEqual(item["status"], "BACKUP_CREATED")
            with sqlite3.connect(backups / item["filename"]) as db:
                self.assertEqual(db.execute("SELECT tenant_id, subject_id, key FROM tenant_state").fetchone(), ("tenant-a", "user-a", "prefs"))

    def test_missing_optional_provider_databases_are_reported_as_not_initialized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            result = SQLiteBackupService(runtime, backups).backup(["ctrader_oauth_tokens"])
        self.assertEqual(result["results"][0]["status"], "NOT_INITIALIZED")

    def test_every_persistent_tenant_store_is_in_backup_allowlist(self):
        expected = {
            "tenant_market_data": "tenant-connection-timeframe-monitor.sqlite3",
            "tenant_tradingview_alerts": "tenant-tradingview-alerts.sqlite3",
            "mt5_relay_tokens": "tenant-mt5-relay-tokens.sqlite3",
            "tradingview_webhook_secrets": "tenant-tradingview-webhook-secrets.sqlite3",
            "ctrader_oauth_state": "tenant-ctrader-oauth-state.sqlite3",
            "ctrader_oauth_tokens": "tenant-ctrader-oauth-tokens.sqlite3",
            "tenant_signal_evidence": "tenant-signal-evidence.sqlite3",
            "news_evidence": "news-evidence.sqlite3",
            "economic_calendar": "economic-calendar.sqlite3",
        }
        for database_id, filename in expected.items():
            with self.subTest(database_id=database_id):
                self.assertEqual(BACKUP_DATABASES[database_id], filename)

    def test_backup_rejects_symlink_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            real = runtime / "real.sqlite3"
            with sqlite3.connect(real) as db:
                db.execute("CREATE TABLE sample (id INTEGER)")
            source = runtime / "tenant-state.sqlite3"
            try:
                source.symlink_to(real)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable in this environment")
            result = SQLiteBackupService(runtime, backups).backup(["tenant_state"])
            self.assertEqual(result["results"][0]["status"], "SOURCE_UNSAFE")

    def test_backup_rejects_broken_foreign_key_relationships(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            source = runtime / "decision-memory.sqlite3"
            with sqlite3.connect(source) as db:
                db.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
                db.execute("CREATE TABLE children (parent_id INTEGER REFERENCES parents(id))")
                db.execute("PRAGMA foreign_keys = OFF")
                db.execute("INSERT INTO children(parent_id) VALUES (404)")
            result = SQLiteBackupService(runtime, backups).backup(["decision_memory"])
            self.assertEqual(result["results"][0]["status"], "BACKUP_FAILED")
            self.assertEqual(list(backups.glob("decision_memory-*.sqlite3")), [])

    def test_rejects_unknown_database_identifier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                SQLiteBackupService(root / "runtime", root / "backups").backup(["arbitrary_path"])

    def test_rejects_backup_inside_runtime_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            runtime.mkdir()
            with self.assertRaises(ValueError):
                SQLiteBackupService(runtime, runtime / "backups")


    def test_restore_verification_rejects_corrupt_backup_and_cleans_temporary_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            backups.mkdir()
            filename = "decision_memory-20261127T010203000000Z.sqlite3"
            (backups / filename).write_bytes(b"not a sqlite database")
            result = SQLiteBackupService(runtime, backups).verify_restore(
                "decision_memory", filename
            )
            self.assertEqual(result["status"], "RESTORE_VALIDATION_FAILED")
            self.assertEqual(result["error_class"], "DatabaseError")
            self.assertFalse(result["live_database_modified"])
            self.assertFalse(list(backups.glob(".decision_memory-restore-test-*")))

    def test_restore_verification_rejects_symlink_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            backups.mkdir()
            outside = root / "outside.sqlite3"
            with sqlite3.connect(outside) as db:
                db.execute("CREATE TABLE sample (id INTEGER)")
            filename = "decision_memory-20261127T010203000000Z.sqlite3"
            link = backups / filename
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable in this environment")
            with self.assertRaisesRegex(ValueError, "existing regular file"):
                SQLiteBackupService(runtime, backups).verify_restore(
                    "decision_memory", filename
                )



    def test_tenant_market_data_database_is_included_in_allowlisted_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            source = runtime / "tenant-connection-timeframe-monitor.sqlite3"
            with sqlite3.connect(source) as db:
                db.execute(
                    "CREATE TABLE tenant_connection_timeframe_results "
                    "(tenant_id TEXT, subject_id TEXT, connection_id TEXT, result_json TEXT)"
                )
                db.execute(
                    "INSERT INTO tenant_connection_timeframe_results VALUES (?, ?, ?, ?)",
                    ("tenant-a", "user-a", "connection-1", '{"signal":"AGUARDAR"}'),
                )
                db.execute(
                    "CREATE TABLE tenant_connection_timeframe_processing_lease "
                    "(lease_key TEXT, owner_token TEXT, expires_at REAL)"
                )
                db.execute(
                    """
                    CREATE TABLE tenant_connection_notification_outbox (
                        event_id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        subject_id TEXT NOT NULL,
                        connection_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        candle_at TEXT NOT NULL,
                        result_json TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        lease_until REAL,
                        lease_token TEXT,
                        delivered_at REAL,
                        dead_at REAL,
                        last_error TEXT
                    )
                    """
                )
                db.execute(
                    "INSERT INTO tenant_connection_timeframe_processing_lease "
                    "VALUES (?, ?, ?)",
                    ("lease-a", "worker-a", 9999999999.0),
                )
                db.execute(
                    """
                    INSERT INTO tenant_connection_notification_outbox (
                        event_id, tenant_id, subject_id, connection_id, symbol,
                        timeframe, candle_at, result_json, created_at, attempts,
                        lease_until, lease_token, delivered_at, dead_at, last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "event-a", "tenant-a", "user-a", "connection-1",
                        "EURUSD", "5m", "2026-11-27T12:00:00+00:00",
                        '{"signal":"AGUARDAR"}', 1795780800.0, 0,
                        None, None, None, None, None,
                    ),
                )
            result = SQLiteBackupService(runtime, backups).backup(["tenant_market_data"])
            item = result["results"][0]
            self.assertEqual(item["status"], "BACKUP_CREATED")
            with sqlite3.connect(backups / item["filename"]) as db:
                self.assertEqual(
                    db.execute(
                        "SELECT tenant_id, subject_id, connection_id FROM "
                        "tenant_connection_timeframe_results"
                    ).fetchone(),
                    ("tenant-a", "user-a", "connection-1"),
                )
                self.assertEqual(
                    db.execute(
                        "SELECT COUNT(*) FROM tenant_connection_timeframe_processing_lease"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    db.execute(
                        "SELECT COUNT(*) FROM tenant_connection_notification_outbox"
                    ).fetchone()[0],
                    1,
                )



    def test_tenant_tradingview_alert_history_is_included_in_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            source = runtime / "tenant-tradingview-alerts.sqlite3"
            with sqlite3.connect(source) as db:
                db.execute(
                    "CREATE TABLE tenant_tradingview_alert_events "
                    "(tenant_id TEXT, subject_id TEXT, connection_id TEXT, event_id TEXT, payload_json TEXT)"
                )
                db.execute(
                    "INSERT INTO tenant_tradingview_alert_events VALUES (?, ?, ?, ?, ?)",
                    ("tenant-a", "user-a", "connection-1", "event-0001", '{"action":"BUY"}'),
                )
            result = SQLiteBackupService(runtime, backups).backup(["tenant_tradingview_alerts"])
            item = result["results"][0]
            self.assertEqual(item["status"], "BACKUP_CREATED")
            with sqlite3.connect(backups / item["filename"]) as db:
                self.assertEqual(
                    db.execute(
                        "SELECT tenant_id, subject_id, connection_id, event_id "
                        "FROM tenant_tradingview_alert_events"
                    ).fetchone(),
                    ("tenant-a", "user-a", "connection-1", "event-0001"),
                )




def test_missing_news_and_calendar_stores_are_optional_until_configured():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        runtime = root / "runtime"
        backups = root / "backups"
        runtime.mkdir()
        result = SQLiteBackupService(runtime, backups).backup(
            ["news_evidence", "economic_calendar", "tenant_signal_evidence"]
        )
    assert [item["status"] for item in result["results"]] == [
        "NOT_INITIALIZED", "NOT_INITIALIZED", "NOT_INITIALIZED"
    ]


def test_news_and_calendar_stores_are_backed_up_when_present():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        runtime = root / "runtime"
        backups = root / "backups"
        runtime.mkdir()
        news = runtime / "news-evidence.sqlite3"
        calendar = runtime / "economic-calendar.sqlite3"
        with sqlite3.connect(news) as db:
            db.execute("CREATE TABLE tenant_news_evidence (tenant_id TEXT, subject_id TEXT)")
            db.execute("INSERT INTO tenant_news_evidence VALUES ('tenant-a','alice')")
        with sqlite3.connect(calendar) as db:
            db.execute("CREATE TABLE economic_calendar_observations (source_id TEXT, source_event_id TEXT)")
            db.execute("INSERT INTO economic_calendar_observations VALUES ('bls','cpi-1')")

        result = SQLiteBackupService(runtime, backups).backup(
            ["news_evidence", "economic_calendar"]
        )

        assert [item["status"] for item in result["results"]] == [
            "BACKUP_CREATED", "BACKUP_CREATED"
        ]
        for item in result["results"]:
            assert (backups / item["filename"]).is_file()

if __name__ == "__main__":
    unittest.main()
