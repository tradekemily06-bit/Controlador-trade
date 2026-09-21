from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage.scoped_state_store import MAX_PAYLOAD_BYTES as MAX_STATE_PAYLOAD_BYTES, SQLiteScopedStateStore
from storage.sqlite_production_store import SQLiteProductionStore


class SQLiteIsolationHardeningTests(unittest.TestCase):
    def test_scoped_state_isolation_and_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteScopedStateStore(Path(tmp) / "state.db")
            store.put(tenant_id="tenant-a", subject_id="user-a", namespace="prefs", payload={"value": "a"})
            store.put(tenant_id="tenant-a", subject_id="user-b", namespace="prefs", payload={"value": "b"})
            store.put(tenant_id="tenant-b", subject_id="user-a", namespace="prefs", payload={"value": "c"})

            self.assertEqual(store.get(tenant_id="tenant-a", subject_id="user-a", namespace="prefs"), {"value": "a"})
            self.assertEqual(store.get(tenant_id="tenant-a", subject_id="user-b", namespace="prefs"), {"value": "b"})
            self.assertIsNone(store.get(tenant_id="tenant-b", subject_id="user-b", namespace="prefs"))

            with self.assertRaises(ValueError):
                store.put(tenant_id="t", subject_id="u", namespace="prefs", payload="x" * MAX_STATE_PAYLOAD_BYTES)

            with self.assertRaises(ValueError):
                store.get(tenant_id="t" * 257, subject_id="u", namespace="prefs")

    def test_scoped_state_rejects_symlink_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real.db"
            SQLiteScopedStateStore(real)
            link = root / "link.db"
            link.symlink_to(real)
            with self.assertRaises(RuntimeError):
                SQLiteScopedStateStore(link)

    def test_production_store_isolation_and_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteProductionStore(Path(tmp) / "production.db")
            record = {"decision_id": "d1", "signal": "COMPRA"}
            store.save(record, tenant_id="tenant-a", subject_id="user-a")
            store.save({"decision_id": "d2", "signal": "VENDA"}, tenant_id="tenant-a", subject_id="user-b")
            store.save({"decision_id": "d3", "signal": "AGUARDAR"}, tenant_id="tenant-b", subject_id="user-a")

            self.assertEqual(store.load("d1", tenant_id="tenant-a", subject_id="user-a"), record)
            self.assertIsNone(store.load("d1", tenant_id="tenant-a", subject_id="user-b"))
            self.assertEqual(store.list(tenant_id="tenant-a", subject_id="user-a"), [record])

            with self.assertRaises(ValueError):
                store.load("d1", tenant_id="tenant-a" * 100, subject_id="user-a")
            with self.assertRaises(ValueError):
                store.list(tenant_id="tenant-a", subject_id="user-a", limit=True)

    def test_production_store_rejects_symlink_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real.db"
            SQLiteProductionStore(real)
            link = root / "link.db"
            link.symlink_to(real)
            with self.assertRaises(RuntimeError):
                SQLiteProductionStore(link)


if __name__ == "__main__":
    unittest.main()
