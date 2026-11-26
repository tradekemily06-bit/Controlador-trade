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
