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
