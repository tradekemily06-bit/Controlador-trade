from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.sqlite_backup_service import SQLiteBackupService


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

    def test_tenant_signal_evidence_and_outcomes_are_included_in_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            backups = root / "backups"
            runtime.mkdir()
            from analysis.tenant_signal_evidence_store import TenantSignalEvidenceStore
            from analysis.tenant_signal_outcome_store import TenantSignalOutcomeStore
            from security.tenant_context import TenantContext

            evidence = TenantSignalEvidenceStore(runtime / "tenant-signal-evidence.sqlite3")
            outcomes = TenantSignalOutcomeStore(evidence)
            owner = TenantContext("tenant-a", "subject-a")
            evidence.record_signal(
                owner, signal_id="signal-1", symbol="EURUSD", timeframe="M1",
                direction="COMPRA", model_version="test-v1", evidence_score=70,
                score_semantics="EVIDENCE_STRENGTH_NOT_WIN_PROBABILITY",
                candle_close_at="2026-11-27T10:01:00Z",
                observed_at="2026-11-27T10:01:02Z",
                valid_until="2026-11-27T10:02:00Z",
                provenance="REAL_MARKET_DATA",
            )
            outcomes.resolve(owner, "signal-1", {
                "symbol": "EURUSD", "timeframe": "M1",
                "open_time": "2026-11-27T10:01:00Z",
                "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15,
            }, provenance="REAL_MARKET_DATA")

            result = SQLiteBackupService(runtime, backups).backup(["tenant_signal_evidence"])
            item = result["results"][0]
            self.assertEqual(item["status"], "BACKUP_CREATED")
            with sqlite3.connect(backups / item["filename"]) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_signal_evidence").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM tenant_signal_outcomes").fetchone()[0], 1)
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

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


if __name__ == "__main__":
    unittest.main()
