from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analysis.decision_store import DecisionStore


class DecisionStorePersistenceTests(unittest.TestCase):
    def test_unconfigured_store_reports_memory_only_mode(self):
        with patch.dict("os.environ", {"CONTROLADOR_DECISION_DB": ""}, clear=False):
            store = DecisionStore(database_path="")
        status = store.persistence_status()
        self.assertEqual(status["mode"], "IN_MEMORY")
        self.assertEqual(status["state"], "IN_MEMORY_NOT_CONFIGURED")
        self.assertFalse(status["durability_confirmed"])

    def test_configured_store_reports_sqlite_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DecisionStore(str(Path(directory) / "decisions.sqlite3"))
            status = store.persistence_status()
            self.assertEqual(status["mode"], "SQLITE")
            self.assertEqual(status["state"], "PERSISTENT_READY")
            self.assertTrue(status["durability_confirmed"])

    def test_initialization_failure_is_visible_and_not_relabelled_as_memory_success(self):
        with tempfile.TemporaryDirectory() as directory:
            blocked_parent = Path(directory) / "a-file"
            blocked_parent.write_text("not a directory", encoding="utf-8")
            store = DecisionStore(str(blocked_parent / "decisions.sqlite3"))
            status = store.persistence_status()
            self.assertEqual(status["state"], "PERSISTENCE_ERROR")
            self.assertFalse(status["durability_confirmed"])
            self.assertEqual(status["last_error_class"], "NotADirectoryError")


if __name__ == "__main__":
    unittest.main()
