from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from security.tenant_context import TenantContext
from security.sqlite_tenant_storage import SQLiteTenantStorage


class SQLiteTenantStorageTests(unittest.TestCase):
    def test_values_are_isolated_by_tenant_and_survive_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "tenant-state.sqlite3"
            tenant_a = TenantContext("tenant-a", "user-a")
            tenant_b = TenantContext("tenant-b", "user-b")

            first = SQLiteTenantStorage(database)
            first.put(tenant_a, "preferences", {"theme": "dark"})
            first.put(tenant_b, "preferences", {"theme": "light"})

            reopened = SQLiteTenantStorage(database)
            self.assertEqual(reopened.get(tenant_a, "preferences"), {"theme": "dark"})
            self.assertEqual(reopened.get(tenant_b, "preferences"), {"theme": "light"})

            reopened.delete(tenant_a, "preferences")
            self.assertIsNone(reopened.get(tenant_a, "preferences"))
            self.assertEqual(reopened.get(tenant_b, "preferences"), {"theme": "light"})

    def test_missing_context_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteTenantStorage(Path(directory) / "tenant.sqlite3")
            with self.assertRaises(PermissionError):
                storage.get(None, "preferences")  # type: ignore[arg-type]
            with self.assertRaises(PermissionError):
                storage.put(None, "preferences", {})  # type: ignore[arg-type]
            with self.assertRaises(PermissionError):
                storage.delete(None, "preferences")  # type: ignore[arg-type]

    def test_invalid_keys_and_non_json_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteTenantStorage(Path(directory) / "tenant.sqlite3")
            tenant = TenantContext("tenant-a", "user-a")
            with self.assertRaises(ValueError):
                storage.get(tenant, " ")
            with self.assertRaises(ValueError):
                storage.get(tenant, "x" * 201)
            with self.assertRaises(ValueError):
                storage.put(tenant, "invalid", float("nan"))

    def test_local_sqlite_does_not_claim_production_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteTenantStorage(Path(directory) / "tenant.sqlite3")
            self.assertFalse(storage.production_durable)
            self.assertFalse(storage.ready_for_production)


if __name__ == "__main__":
    unittest.main()
